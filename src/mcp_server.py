"""
MCP-сервер PowerMill AI: ассистент как инструмент для ИИ-клиента.

Зачем это нужно
---------------
У современного ИИ-клиента (Claude Desktop, Cursor, VS Code, Windsurf) есть
подключения MCP: клиент сам вызывает наши инструменты и сам показывает ответ.
Тогда не нужно ни окно, ни браузер: человек пишет в чат «посчитай режимы для
40Х фрезой D16» или «покажи, что открыто в PowerMill», а работают наши функции.

Что здесь важно
---------------
* **Свой протокол, без зависимостей.** Официальный пакет `mcp` тянет pydantic,
  anyio и т.п. Нам нужна маленькая часть: `initialize`, `tools/list`,
  `tools/call`, `resources/list`, `resources/read`. Она реализована здесь
  вручную, поэтому сервер запускается на том же Python, что и всё остальное,
  и его можно проверить тестами без ИИ и без PowerMill.
* **Стандартный ввод-вывод — только протокол.** Всё, что печатают наши
  сценарии, перехватывается и уходит в ответ инструмента (и в stderr). Иначе
  одна случайная строка `print` сломала бы связь с клиентом.
* **Изменяет проект только один инструмент** — `powermill_run_macro`, и только
  с подтверждением `confirm=true` и только макросы из наших папок
  (`PM_AI_*.mac`). Остальные инструменты считают, читают и показывают.
* Клиент не должен видеть простыни: вывод обрезается (`MAX_TOOL_OUTPUT`), а
  длинные отчёты отдаются ресурсами `powermill://report/<файл>`.

Запуск (обычно его запускает сам ИИ-клиент, см. scripts\\\\mcp_setup.py)::

    python -m scripts.mcp_server              # сервер на stdio (для клиента)
    python -m scripts.mcp_server --selftest   # проверить себя и выйти
    python -m scripts.mcp_server --tools      # список инструментов человеку
"""
from __future__ import annotations

import io
import json
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SERVER_NAME = "powermill-ai"
SERVER_VERSION = "0.1"

# Версии протокола, которые мы понимаем. Клиент присылает свою — если она наша,
# отвечаем ею же; иначе отвечаем самой новой из своих, и клиент решает, подходит
# ли ему это (так работает согласование в MCP).
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_PROTOCOL = PROTOCOL_VERSIONS[0]

# Сколько символов вывода сценария отдаём в ответе (клиент не должен давиться)
MAX_TOOL_OUTPUT = 6000
# Сколько байт отчёта отдаём как ресурс
MAX_RESOURCE_BYTES = 300_000

INSTRUCTIONS = """\
Ты работаешь с ассистентом технолога PowerMill AI (Autodesk PowerMill).

Как этим пользоваться:
1. Сначала посмотри состояние: powermill_status — запущен ли PowerMill, что
   открыто в проекте, есть ли связь. Без связи остальные действия бессмысленны.
2. Режимы резания всегда считай инструментом powermill_cutting: это формулы,
   без выдумок. Не называй числа по памяти.
3. Перед тем как что-то менять в проекте, покажи план: powermill_plan_operation
   (или powermill_macro, чтобы получить текст макроса). Технолог должен увидеть
   числа и команды ДО выполнения.
4. Меняет проект только powermill_run_macro с confirm=true, и только наши
   макросы. Изменения — только на копии проекта (Деталь_AI.pmlprj).
5. Ассистент не проверяет допуски по чертежу, не гарантирует поведение станка и
   не заменяет технолога: об этом говори прямо.
"""


# --------------------------------------------------------------------------
# Инструмент
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ToolSpec:
    """Один инструмент MCP: что вызывать, чем и что отвечает."""

    name: str
    description: str
    input_schema: dict
    handler: Callable[..., str]
    modifies_project: bool = False

    def as_dict(self) -> dict:
        return {"name": self.name, "description": self.description,
                "inputSchema": self.input_schema}


class ToolError(RuntimeError):
    """Ошибка внутри инструмента: показывается человеку, сервер не падает."""


def _schema(properties: dict | None = None, required: tuple[str, ...] = (),
            **extra: Any) -> dict:
    schema: dict = {"type": "object",
                    "properties": properties or {},
                    "additionalProperties": False}
    if required:
        schema["required"] = list(required)
    schema.update(extra)
    return schema


def _text(value: Any, empty: str = "(пусто)") -> str:
    text = str(value).strip()
    return text or empty


def _cut(text: str, limit: int = MAX_TOOL_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    return (text[:limit] +
            f"\n… (обрезано: всего {len(text)} символов; полный текст — в отчёте, "
            f"см. пункт 29)")


# --------------------------------------------------------------------------
# Ленивый ассистент: тяжёлые библиотеки поднимаем только при первом вопросе
# --------------------------------------------------------------------------
_ASSISTANT = None


def assistant():
    """Чат-ассистент (поиск по справке, макросы, разборы). Создаётся один раз."""
    global _ASSISTANT
    if _ASSISTANT is None:
        from src.rag import PowerMillAI

        _ASSISTANT = PowerMillAI(verbose=False)
    return _ASSISTANT


# --------------------------------------------------------------------------
# Наши инструменты
# --------------------------------------------------------------------------
def tool_status() -> str:
    """Связь и проект: запущен ли PowerMill, что в нём открыто."""
    import config
    from src import link_check, project_context

    lines = [f"Папка данных: {config.DATA_ROOT}"]
    report = link_check.run(with_roundtrip=False)
    lines.extend(report.format().splitlines())
    lines.append("ИТОГ: " + report.summary())
    lines.append("")
    lines.append("Полная проверка связи (с выполнением макроса внутри PowerMill) — "
                 "кнопка «Связь с PowerMill» в окне или пункт 41 меню.")
    context = project_context.load()
    if context:
        try:
            lines.append("")
            lines.append(project_context.summary(context))
        except Exception:                                     # noqa: BLE001
            pass
    return "\n".join(lines)


def tool_cutting(request: str) -> str:
    """Режимы резания: детерминированный расчёт по формулам (без ИИ)."""
    from src import cutting

    text, data = cutting.answer(request)
    note = []
    if not data.get("material"):
        note.append("(!) Материал не распознан — считал по значению по умолчанию. "
                    "Назови материал точнее (например «Сталь 40Х»).")
    note.append("Числа посчитаны формулами того же калькулятора, что в пункте 3 "
                "меню: это рекомендация, а не гарантия станка.")
    return "\n".join([text, "", *note])


def tool_error(error_text: str) -> str:
    """Разбор ошибки PowerMill: причина и что делать."""
    return assistant().error(error_text)


def tool_compare(query: str) -> str:
    """Сравнить две стратегии или два инструмента (таблица)."""
    return assistant().compare(query)


def tool_ask(question: str) -> str:
    """Вопрос по справке PowerMill (ищет в разобранной документации)."""
    ai = assistant()
    try:
        return ai.ask(question)
    except Exception as error:                                # noqa: BLE001
        # ИИ может быть не настроен (нет ключа и Ollama) — тогда отдаём то, что
        # нашлось в справке, и объясняем, как включить ответы.
        found = ""
        try:
            found = ai.sources(question)
        except Exception:                                     # noqa: BLE001
            pass
        return ("Ответ ИИ недоступен: " + _text(error) +
                "\n\nВключается так: пункт 21 меню (ключ API) или Ollama "
                "(пункт 22 — переключение).\n\nЧто нашлось в справке:\n" + found)


def tool_macro(task: str) -> str:
    """PML-макрос по задаче: текст, проверка по словарю и путь к .mac файлу."""
    return assistant().macro(task, save=True)


def tool_plan_operation(material: str = "Сталь 40Х", tool_diameter: float = 16.0,
                        tool_name: str = "", stepover: float | None = None,
                        stepdown: float | None = None, allowance: float = 0.0,
                        tool_from_project: bool = False,
                        nc_after: bool = False) -> str:
    """План черновой операции с числами — ДО любых изменений в проекте."""
    from src import pm_flow

    request = pm_flow.FlowRequest(
        material=material,
        tool_diameter=float(tool_diameter),
        tool_name=tool_name or f"D{float(tool_diameter):g}_Freza",
        stepover=stepover,
        stepdown=stepdown,
        allowance=float(allowance),
        tool_from_project=bool(tool_from_project),
        nc_after=bool(nc_after),
        calculate=True,
    )
    plan, lines = pm_flow.build_plan(request)
    warnings = pm_flow.warnings_for(request)
    out = ["План черновой операции (ничего ещё не сделано):", "", *lines]
    if warnings:
        out += ["", "На что посмотреть:"] + [f"  • {item}" for item in warnings]
    out += [
        "",
        "Чтобы выполнить: технолог подтверждает — и запускается макрос в PowerMill "
        "(в окне это кнопка «Черновая операция», пункт 31; полный поток с "
        "проверками и NC — «СДЕЛАЙ», пункт 37).",
        "Важно: изменения вносятся только в копию проекта (Деталь_AI.pmlprj).",
        f"Служебные числа плана: {plan.toolpath_name}, ap={plan.stepdown}, "
        f"ae={plan.stepover}, S={plan.rpm}, F={plan.feed}.",
    ]
    return "\n".join(out)


def macro_folder() -> Path:
    """Папка наших макросов (то, что можно выполнять)."""
    from src import pm_macro

    return Path(pm_macro.MACRO_DIR)


def allowed_macros() -> list[Path]:
    """Макросы, которые разрешено выполнять: только наши, PM_AI_*.mac."""
    from src import pm_buttons, pm_macro

    folders = [macro_folder()] + [PROJECT_ROOT / name
                                 for name in pm_buttons.MACRO_FOLDERS]
    found: list[Path] = []
    for folder in folders:
        try:
            for path in sorted(Path(folder).glob("PM_AI_*.mac")):
                if path not in found:
                    found.append(path)
        except OSError:
            continue
    return found


def find_macro(name: str) -> Path | None:
    """Ищет макрос по имени: «PM_AI_TEST», «test», «PM_AI_TEST.mac»."""
    wanted = name.strip()
    if not wanted:
        return None
    if not wanted.lower().endswith(".mac"):
        wanted += ".mac"
    if not wanted.upper().startswith("PM_AI_"):
        wanted = "PM_AI_" + wanted.upper()
    for path in allowed_macros():
        if path.name.lower() == wanted.lower():
            return path
    return None


def tool_run_macro(name: str, confirm: bool = False) -> str:
    """Выполнить наш макрос ВНУТРИ PowerMill. Только с подтверждением."""
    if not confirm:
        variants = ", ".join(path.stem for path in allowed_macros()[:6]) or "нет"
        return ("Не выполнил: нужен confirm=true.\n"
                "Это единственный инструмент, который меняет проект, поэтому он "
                "работает только по явному подтверждению технолога.\n"
                f"Наши макросы: {variants}…\n"
                "Сначала покажи технологу, что именно сделает макрос "
                "(powermill_macro или powermill_plan_operation).")

    path = find_macro(name)
    if path is None:
        found = ", ".join(item.stem for item in allowed_macros()) or "нет ни одного"
        return (f"Не нашёл макрос «{name}». Выполнять можно только наши макросы "
                f"(PM_AI_*.mac).\nЕсть: {found}.\n"
                "Если макросов ещё нет — их создаёт пункт 28 меню "
                "(он же копирует их в папку макросов PowerMill).")

    from src import pm_com

    session, message = pm_com.connect()
    if session is None:
        return (f"PowerMill не отвечает: {message}\n"
                "Открой PowerMill с проектом и повтори. Проверить связь: "
                "powermill_status или пункт 41 меню.")
    command = f'MACRO "{str(path).replace(chr(92), "/")}"'
    ok, note = session.execute(command)
    return (("✔ " if ok else "✘ ") + f"Выполнил внутри PowerMill: {path.name}\n"
            f"Ответ PowerMill: {note}\n"
            "Что изменилось — смотри отчёты (пункт 29) и проверки (пункт 35).")


def tool_read_report(name: str = "doctor_report.txt") -> str:
    """Прочитать отчёт из папки данных (те, что видно в пункте 29 меню)."""
    import config

    folder = Path(config.OUTPUT_DIR)
    safe = Path(name).name                        # никаких путей наружу
    path = folder / safe
    if not path.exists():
        known = ", ".join(item[0] for item in REPORTS[:8])
        return f"Отчёта «{safe}» нет в {folder}.\nОбычно есть: {known}…"
    text = _read_text(path)
    return f"Отчёт {safe} ({path}):\n\n" + text


# --------------------------------------------------------------------------
# Ресурсы: отчёты целиком
# --------------------------------------------------------------------------
REPORTS: tuple[tuple[str, str], ...] = (
    ("doctor_report.txt", "Проверка компьютера: что готово, что нет (пункт 40)"),
    ("pm_link_report.txt", "Связь с PowerMill: проверка делом (пункт 41)"),
    ("pm_flow_report.txt", "Полный поток «СДЕЛАЙ»: план, выполнение, проверки, NC"),
    ("pm_operation_report.txt", "Черновая операция: что собралось (пункт 31)"),
    ("pm_check_report.txt", "Проверки траекторий: зарезы и столкновения (пункт 35)"),
    ("pm_nc_report.txt", "NC-программа (пункт 36)"),
    ("pm_tool_report.txt", "Фреза в проекте: команды и ответы (пункт 33)"),
    ("pm_ribbon_report.txt", "Вкладка на ленте PowerMill (пункт 34)"),
    ("plugin_report.txt", "Каркас плагина (пункт 25)"),
    ("pm_plugin_build_report.txt", "Сборка плагина-панели (пункт 38)"),
    ("pm_macros_report.txt", "Макросы для PowerMill (пункт 28)"),
    ("pm_api_probe.txt", "Разведка API PowerMill (пункт 27)"),
    ("project_context.json", "Снимок проекта (пункт 24)"),
    ("vector_db_report.txt", "Векторная база: сколько записей (пункт 6)"),
    ("install_packages_report.txt", "Библиотеки: что стоит (пункт 43)"),
    ("data_root_report.txt", "Смена папки данных (пункт 42)"),
    ("mcp_report.txt", "Подключение к ИИ-клиенту по MCP (пункт 44)"),
    ("install_report.txt", "Установка программы"),
    ("uninstall_report.txt", "Удаление программы"),
)


def _read_text(path: Path) -> str:
    try:
        data = path.read_bytes()[:MAX_RESOURCE_BYTES]
    except OSError as error:
        return f"(не удалось прочитать: {error})"
    text = data.decode("utf-8", errors="replace")
    if path.stat().st_size > MAX_RESOURCE_BYTES:
        text += (f"\n… (файл больше {MAX_RESOURCE_BYTES // 1000} КБ, показана "
                 f"часть)")
    return text


def resource_list() -> list[dict]:
    import config

    folder = Path(config.OUTPUT_DIR)
    items = [{
        "uri": "powermill://status",
        "name": "Состояние PowerMill AI",
        "description": "Связь с PowerMill, папка данных, что открыто в проекте",
        "mimeType": "text/plain",
    }]
    for name, title in REPORTS:
        if (folder / name).exists():
            items.append({
                "uri": f"powermill://report/{name}",
                "name": name,
                "description": title,
                "mimeType": ("application/json" if name.endswith(".json")
                             else "text/plain"),
            })
    return items


def resource_read(uri: str) -> dict:
    import config

    if uri in ("powermill://status", "powermill://status.txt"):
        text = tool_status()
        return {"uri": uri, "mimeType": "text/plain", "text": text}
    marker = "powermill://report/"
    if uri.startswith(marker):
        name = Path(uri[len(marker):]).name
        path = Path(config.OUTPUT_DIR) / name
        if not path.exists():
            raise ToolError(f"отчёта «{name}» нет; список — resources/list")
        return {"uri": uri,
                "mimeType": ("application/json" if name.endswith(".json")
                             else "text/plain"),
                "text": _read_text(path)}
    raise ToolError(f"неизвестный ресурс: {uri}")


# --------------------------------------------------------------------------
# Список инструментов
# --------------------------------------------------------------------------
def build_tools() -> list[ToolSpec]:
    return [
        ToolSpec(
            "powermill_status",
            "Состояние PowerMill AI: запущен ли PowerMill, есть ли связь, какая "
            "папка данных, что открыто в проекте. Начни с этого.",
            _schema(),
            lambda: tool_status(),
        ),
        ToolSpec(
            "powermill_cutting",
            "Режимы резания (S, F, ap, ae, мощность) по материалу и фрезе — "
            "детерминированный расчёт формулами, без ИИ.",
            _schema({
                "request": {"type": "string",
                            "description": "Например: «Сталь 40Х, фреза D16, "
                                           "черновая»"},
            }, ("request",)),
            lambda request: tool_cutting(request),
        ),
        ToolSpec(
            "powermill_ask",
            "Вопрос по справке PowerMill (ищет в разобранной документации).",
            _schema({"question": {"type": "string"}}, ("question",)),
            lambda question: tool_ask(question),
        ),
        ToolSpec(
            "powermill_error",
            "Разбор ошибки PowerMill: причина, варианты решения.",
            _schema({"error_text": {"type": "string",
                                    "description": "Текст ошибки из PowerMill"}},
                    ("error_text",)),
            lambda error_text: tool_error(error_text),
        ),
        ToolSpec(
            "powermill_compare",
            "Сравнить две стратегии обработки или два инструмента (таблица).",
            _schema({"query": {"type": "string",
                               "description": "Например: «Model Area Clearance и "
                                              "Offset Area Clearance»"}},
                    ("query",)),
            lambda query: tool_compare(query),
        ),
        ToolSpec(
            "powermill_macro",
            "Составить PML-макрос по задаче: текст, проверка по словарю PML и "
            "сохранение в .mac. Ничего не выполняет.",
            _schema({"task": {"type": "string",
                              "description": "Что должен делать макрос"}},
                    ("task",)),
            lambda task: tool_macro(task),
        ),
        ToolSpec(
            "powermill_plan_operation",
            "План черновой операции с числами (фреза, заготовка, траектория, "
            "режимы, проверки) — ДО любых изменений в проекте.",
            _schema({
                "material": {"type": "string", "default": "Сталь 40Х"},
                "tool_diameter": {"type": "number", "default": 16},
                "tool_name": {"type": "string", "default": ""},
                "stepover": {"type": "number",
                             "description": "Шаг по XY, мм (пусто — из расчёта)"},
                "stepdown": {"type": "number",
                             "description": "Заглубление, мм (пусто — из расчёта)"},
                "allowance": {"type": "number", "default": 0,
                              "description": "Припуск на чистовую, мм"},
                "tool_from_project": {"type": "boolean", "default": False},
                "nc_after": {"type": "boolean", "default": False},
            }),
            lambda **kwargs: tool_plan_operation(**kwargs),
        ),
        ToolSpec(
            "powermill_run_macro",
            "Выполнить НАШ макрос внутри PowerMill (PM_AI_*.mac). Это меняет "
            "проект: только с confirm=true и после показа плана технологу.",
            _schema({
                "name": {"type": "string",
                         "description": "Имя макроса, например «test» или "
                                        "«PM_AI_TEST.mac»"},
                "confirm": {"type": "boolean", "default": False,
                            "description": "true — технолог подтвердил"},
            }, ("name",)),
            lambda name, confirm=False: tool_run_macro(name, confirm),
            modifies_project=True,
        ),
        ToolSpec(
            "powermill_read_report",
            "Прочитать отчёт из папки данных (например doctor_report.txt или "
            "pm_link_report.txt).",
            _schema({"name": {"type": "string",
                              "default": "doctor_report.txt"}}),
            lambda name="doctor_report.txt": tool_read_report(name),
        ),
    ]


# --------------------------------------------------------------------------
# Перехват вывода сценариев (чтобы не сломать протокол)
# --------------------------------------------------------------------------
class _Collector(io.TextIOBase):
    """Пишет то, что печатают сценарии: в буфер и в stderr (для логов клиента)."""

    def __init__(self, mirror=None):
        self.buffer: list[str] = []
        self.mirror = mirror

    def write(self, data: str) -> int:
        self.buffer.append(data)
        if self.mirror is not None:
            try:
                self.mirror.write(data)
                self.mirror.flush()
            except Exception:                                 # noqa: BLE001
                pass
        return len(data)

    def flush(self) -> None:
        return None

    def text(self) -> str:
        return "".join(self.buffer).strip()

    def isatty(self) -> bool:
        return False


@contextmanager
def captured_output(mirror=None):
    """Всё, что печатается внутри блока, попадает в буфер, а не в протокол."""
    collector = _Collector(mirror or sys.stderr)
    saved_out, saved_err = sys.stdout, sys.stderr
    sys.stdout = collector
    # stderr тоже туда: часть модулей пишет предупреждения в stderr
    sys.stderr = collector
    try:
        yield collector
    finally:
        sys.stdout, sys.stderr = saved_out, saved_err


# --------------------------------------------------------------------------
# Сервер
# --------------------------------------------------------------------------
MISSING = object()

ERROR_PARSE = -32700
ERROR_INVALID = -32600
ERROR_METHOD = -32601
ERROR_PARAMS = -32602
ERROR_INTERNAL = -32603


class McpServer:
    """Мини-сервер MCP: разбирает сообщение и возвращает ответ (или None).

    Транспорт (stdio, тесты, что угодно) снаружи: это делает сервер проверяемым
    обычными тестами — без клиента, без PowerMill, без ИИ.
    """

    def __init__(self, tools: list[ToolSpec] | None = None,
                 log: list[str] | None = None):
        self.tools = tools if tools is not None else build_tools()
        self.log = log if log is not None else []
        self.initialized = False
        self.client_info: dict = {}

    # ---------------- служебное ----------------
    def tool(self, name: str) -> ToolSpec | None:
        for item in self.tools:
            if item.name == name:
                return item
        return None

    def _error(self, id_, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": id_,
                "error": {"code": code, "message": message}}

    def _result(self, id_, result) -> dict:
        return {"jsonrpc": "2.0", "id": id_, "result": result}

    # ---------------- разбор сообщения ----------------
    def handle(self, message: Any) -> dict | None:
        """Обрабатывает одно сообщение. None — на уведомление отвечать не нужно."""
        if not isinstance(message, dict) or "method" not in message:
            return self._error(message.get("id") if isinstance(message, dict) else None,
                              ERROR_INVALID, "ожидалось сообщение JSON-RPC с method")
        method = message["method"]
        params = message.get("params") or {}
        id_ = message.get("id", MISSING)

        # уведомления (без id) ответа не требуют
        if id_ is MISSING:
            self._notification(method, params)
            return None

        if not isinstance(params, dict):
            return self._error(id_, ERROR_PARAMS, "params должны быть объектом")

        if method == "initialize":
            return self._result(id_, self._initialize(params))
        if method == "ping":
            return self._result(id_, {})
        if method == "tools/list":
            return self._result(id_, {"tools": [item.as_dict()
                                                for item in self.tools]})
        if method == "tools/call":
            return self._tools_call(id_, params)
        if method == "resources/list":
            return self._result(id_, {"resources": resource_list()})
        if method == "resources/templates/list":
            return self._result(id_, {"resourceTemplates": []})
        if method == "resources/read":
            return self._resources_read(id_, params)
        if method == "prompts/list":
            return self._result(id_, {"prompts": []})
        return self._error(id_, ERROR_METHOD, f"метод не поддерживается: {method}")

    def _notification(self, method: str, params: dict) -> None:
        if method == "notifications/initialized":
            self.initialized = True
        self.log.append(f"уведомление: {method}")

    def _initialize(self, params: dict) -> dict:
        asked = params.get("protocolVersion")
        self.client_info = params.get("clientInfo") or {}
        version = asked if asked in PROTOCOL_VERSIONS else DEFAULT_PROTOCOL
        return {
            "protocolVersion": version,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
                "logging": {},
            },
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION,
                           "title": "PowerMill AI — ассистент технолога"},
            "instructions": INSTRUCTIONS,
        }

    def _tools_call(self, id_, params: dict) -> dict:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        spec = self.tool(name) if isinstance(name, str) else None
        if spec is None:
            available = ", ".join(item.name for item in self.tools)
            return self._error(id_, ERROR_PARAMS,
                               f"нет инструмента «{name}». Есть: {available}")
        if not isinstance(arguments, dict):
            return self._error(id_, ERROR_PARAMS, "arguments должны быть объектом")
        return self._result(id_, self._run_tool(spec, arguments))

    def _run_tool(self, spec: ToolSpec, arguments: dict) -> dict:
        unknown = [key for key in arguments
                   if key not in spec.input_schema.get("properties", {})]
        if unknown:
            return self._tool_error(
                spec, "неизвестные аргументы: " + ", ".join(sorted(unknown)) +
                "\nЧто принимает инструмент: " +
                ", ".join(spec.input_schema.get("properties", {})))
        started = time.time()
        try:
            with captured_output() as captured:
                text = spec.handler(**arguments)
        except TypeError as error:                # не тот набор аргументов
            need = spec.input_schema.get("required", [])
            return self._tool_error(spec, f"не хватает аргументов ({error}). "
                                          f"Обязательные: {', '.join(need) or 'нет'}")
        except ToolError as error:
            return self._tool_error(spec, str(error))
        except Exception as error:                # noqa: BLE001
            detail = captured_text = ""
            try:
                detail = f"{type(error).__name__}: {error}"
                import traceback

                traceback.print_exc(file=sys.stderr)
            except Exception:                                 # noqa: BLE001
                pass
            return self._tool_error(spec, "инструмент упал: " + detail)
        spent = time.time() - started
        printed = captured.text()
        if printed:
            text = f"{text}\n\nВывод сценария:\n{printed}"
        self.log.append(f"{spec.name}: {spent:.1f} с, {len(text)} символов")
        return {"content": [{"type": "text", "text": _cut(text)}]}

    def _tool_error(self, spec: ToolSpec, message: str) -> dict:
        self.log.append(f"{spec.name}: ошибка — {message.splitlines()[0][:120]}")
        return {"content": [{"type": "text", "text": _cut(message)}],
                "isError": True}

    def _resources_read(self, id_, params: dict) -> dict:
        uri = params.get("uri")
        if not isinstance(uri, str):
            return self._error(id_, ERROR_PARAMS, "нужен uri")
        try:
            with captured_output():
                content = resource_read(uri)
        except ToolError as error:
            return self._error(id_, ERROR_PARAMS, str(error))
        except Exception as error:                            # noqa: BLE001
            return self._error(id_, ERROR_INTERNAL, f"не смог прочитать: {error}")
        return self._result(id_, {"contents": [content]})

    # ---------------- строка JSON ----------------
    def handle_line(self, line: str) -> str | None:
        """Строка JSON на входе -> строка JSON на выходе (или None)."""
        line = line.strip()
        if not line:
            return None
        try:
            message = json.loads(line)
        except ValueError as error:
            return json.dumps(self._error(None, ERROR_PARSE,
                                          f"не разобрал JSON: {error}"),
                              ensure_ascii=False)
        answer = self.handle(message)
        if answer is None:
            return None
        return json.dumps(answer, ensure_ascii=False)


# --------------------------------------------------------------------------
# Транспорт: стандартный ввод/вывод
# --------------------------------------------------------------------------
def serve(stdin=None, stdout=None, server: McpServer | None = None) -> int:
    """Читает сообщения построчно и отвечает. Так работает MCP по stdio."""
    server = server or McpServer()
    raw_in = getattr(stdin, "buffer", stdin) or sys.stdin.buffer
    raw_out = getattr(stdout, "buffer", stdout) or sys.stdout.buffer
    while True:
        try:
            line = raw_in.readline()
        except KeyboardInterrupt:
            return 0
        if not line:
            return 0
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="replace")
        answer = server.handle_line(line)
        if answer is None:
            continue
        try:
            raw_out.write(answer.encode("utf-8") + b"\n")
            raw_out.flush()
        except (BrokenPipeError, ValueError):
            return 0
        except KeyboardInterrupt:
            return 0


# --------------------------------------------------------------------------
# Самопроверка и справка для человека
# --------------------------------------------------------------------------
def selftest(log=print) -> int:
    """Проверяет сервер без клиента: протокол, инструменты, безопасность."""
    server = McpServer()
    problems: list[str] = []

    def send(message: str) -> dict | None:
        answer = server.handle_line(message)
        return json.loads(answer) if answer else None

    log("=" * 60)
    log("  MCP-СЕРВЕР PowerMill AI — самопроверка")
    log("=" * 60)
    log(f"  Инструментов: {len(server.tools)}")
    log("")

    hello = send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                             "params": {"protocolVersion": PROTOCOL_VERSIONS[-1],
                                        "clientInfo": {"name": "selftest"}}}))
    if not hello or "result" not in hello:
        problems.append("initialize не ответил")
    else:
        result = hello["result"]
        log(f"  ✔ Знакомство: {result['serverInfo']['name']} "
            f"{result['serverInfo']['version']}, протокол {result['protocolVersion']}")
        if result["protocolVersion"] not in PROTOCOL_VERSIONS:
            problems.append("ответили неизвестной версией протокола")

    log("  Уведомление initialized: " +
        ("ответа нет — верно" if send(json.dumps(
            {"jsonrpc": "2.0", "method": "notifications/initialized"})) is None
         else "(!) пришёл ответ"))
    if not server.initialized:
        problems.append("уведомление initialized не учлось")

    listed = send(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))
    tools = ([item["name"] for item in listed["result"]["tools"]]
             if listed and "result" in listed else [])
    log(f"  ✔ Инструменты: {', '.join(tools)}")
    if "powermill_cutting" not in tools:
        problems.append("в списке нет powermill_cutting")

    log("")
    log("  Проверяю расчёт режимов (это чистая математика, PowerMill не нужен):")
    answer = send(json.dumps({
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "powermill_cutting",
                   "arguments": {"request": "Сталь 40Х, фреза D16, черновая"}}}))
    if not answer or "result" not in answer:
        problems.append("инструмента powermill_cutting нет или он не ответил")
        text = "(нет ответа)"
    else:
        text = answer["result"]["content"][0]["text"]
        if answer["result"].get("isError"):
            problems.append("расчёт режимов ответил ошибкой")
    for line in text.splitlines()[:14]:
        log("    " + line)

    log("")
    log("  Проверяю защиту (выполнение макроса без подтверждения):")
    refuse = send(json.dumps({
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {"name": "powermill_run_macro",
                   "arguments": {"name": "PM_AI_TEST"}}}))
    refuse_text = (refuse.get("result", {}).get("content", [{}])[0].get("text", "")
                   if refuse else "")
    if not refuse_text:
        problems.append("инструмент powermill_run_macro не ответил")
    elif "confirm=true" in refuse_text:
        log("    ✔ без confirm=true отказано — так и задумано")
    else:
        problems.append("макрос без подтверждения не отказался")

    unknown = send(json.dumps({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                               "params": {"name": "нет_такого", "arguments": {}}}))
    if unknown and "error" in unknown:
        log("    ✔ несуществующий инструмент — понятная ошибка")
    else:
        problems.append("несуществующий инструмент не дал ошибку")

    resources = send(json.dumps({"jsonrpc": "2.0", "id": 6,
                                 "method": "resources/list"}))
    count = len(resources.get("result", {}).get("resources", [])) if resources else 0
    if resources and "result" in resources:
        log(f"  ✔ Ресурсы (отчёты): {count}")
    else:
        problems.append("resources/list не ответил")

    broken = send("{это не JSON}")
    if broken and "error" in broken:
        log("    ✔ мусор на входе — ошибка разбора, сервер жив")
    else:
        problems.append("на мусор не ответил ошибкой")

    log("")
    if problems:
        log("  ОШИБКИ: " + "; ".join(problems))
        return 2
    log("  ВСЁ В ПОРЯДКЕ. Подключить клиент: пункт 44 меню.")
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="MCP-сервер PowerMill AI (для ИИ-клиентов: Claude, Cursor, VS Code)")
    parser.add_argument("--selftest", action="store_true",
                        help="проверить сервер и выйти (без клиента)")
    parser.add_argument("--tools", action="store_true",
                        help="показать список инструментов человеку")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.tools:
        server = McpServer()
        print(f"MCP-сервер {SERVER_NAME} {SERVER_VERSION}: "
              f"{len(server.tools)} инструментов")
        print()
        for item in server.tools:
            mark = " [меняет проект]" if item.modifies_project else ""
            print(f"  {item.name}{mark}")
            print(f"      {item.description}")
            props = item.input_schema.get("properties", {})
            if props:
                print("      аргументы: " + ", ".join(props))
            print()
        print("Подключить к ИИ-клиенту: пункт 44 меню (scripts\\mcp_setup.bat).")
        return 0

    # Рабочий режим: сервер на стандартном вводе-выводе.
    # В stdout идёт только протокол — поэтому все приветствия печатаем в stderr.
    print(f"{SERVER_NAME} {SERVER_VERSION}: сервер запущен, жду сообщения "
          f"JSON-RPC на stdin", file=sys.stderr)
    return serve()


if __name__ == "__main__":
    sys.exit(main())
