"""
Живой PowerMill через COM — по фактам, которые показала разведка (пункт 27).

Что известно точно (из отчёта `output\\pm_api_probe.txt` на машине технолога,
PowerMill 2026):

    COM-классы: PowerMill.Application, PowerMILL.Application, PowerMILL.Application.1
    Методы приложения: DoCommand, DoCommandEx, Execute, ExecuteEx, Quit, Exit,
                       Visible, WindowState, Busy, Version, GetParameterXML
    Проект: НЕ ActiveProject (такого свойства нет), а Project
    Коллекции проекта: Models, Tools, Toolpaths, Boundaries, Workplanes,
                       Patterns, StockModels, NCPrograms, NCToolpaths,
                       NCWorkplanes, NCTextBlocks, MachineTools,
                       Features, FeatureSets, Levels
    Команда: DoCommand('PRINT "..."') -> OK

Отсюда два важных правила, зашитых в этот модуль:

1. **Присоединяемся, а не создаём.** `win32com.client.Dispatch` запускает новую
   копию PowerMill, если он не открыт (так и вышло при первой разведке).
   Поэтому здесь используется `GetActiveObject` — только к уже запущенному
   PowerMill. Никаких «невидимых второй-копий».
2. **Читаем через коллекции проекта**, а команды выполняем через `DoCommand`.
   Имена коллекций — не догадка, а то, что ответил сам PowerMill.
"""
from __future__ import annotations

from pathlib import Path

try:  # pywin32 может быть не установлен — модуль всё равно должен импортироваться
    import win32com.client as _win32com  # type: ignore
except Exception:  # noqa: BLE001
    _win32com = None

# Порядок важен: первый — то, что ответило на машине технолога
PROGIDS = (
    "PowerMill.Application",
    "PowerMILL.Application",
    "PowerMILL.Application.1",
    "Delcam.PowerMILL.Application",
)

# Раздел контекста проекта -> имя коллекции в объекте Project (проверено разведкой)
COLLECTIONS: dict[str, str] = {
    "models": "Models",
    "stockmodels": "StockModels",
    "boundaries": "Boundaries",
    "patterns": "Patterns",
    "tools": "Tools",
    "toolpaths": "Toolpaths",
    "workplanes": "Workplanes",
    "ncprograms": "NCPrograms",
    "machinetools": "MachineTools",
    "features": "Features",          # FeatureSets/Features в PowerMill
    "levels": "Levels",
}

# Порядок методов для выполнения команд — по отчёту разведки
COMMAND_METHODS = ("DoCommand", "Execute", "DoCommandEx", "ExecuteEx")

# Ограничение: больше этого числа объектов в раздел не тащим
NAME_LIMIT = 500


# --------------------------------------------------------------------------
# Подключение
# --------------------------------------------------------------------------
def bridges() -> dict[str, bool]:
    """Есть ли мосты Python (pythonnet / pywin32)."""
    result: dict[str, bool] = {}
    for module, title in (("clr", "pythonnet (.NET)"),
                          ("win32com.client", "pywin32 (COM)")):
        try:
            __import__(module)
            result[title] = True
        except Exception:  # noqa: BLE001
            result[title] = False
    return result


def attach(progids: tuple[str, ...] = PROGIDS):
    """Присоединяется к УЖЕ ЗАПУЩЕННОМУ PowerMill.

    Возвращает (объект, сообщение). Если PowerMill не запущен — объекта нет:
    запускать его сами не будем, это решение технолога.
    """
    if _win32com is None:
        import sys

        return None, (f"pywin32 не установлен в этом Python: {sys.executable}\n"
                      "   Поставить: пункт 27 меню (он ставит пакеты в тот же "
                      "интерпретатор).")

    # GetActiveObject присоединяется ТОЛЬКО к уже запущенной программе: если
    # PowerMill закрыт, он не откроется (в отличие от Dispatch). Поэтому
    # пробуем всегда, даже если проверка процессов не сработала.
    tried: list[str] = []
    for progid in progids:
        try:
            app = _win32com.GetActiveObject(progid)
            return app, f"подключено к запущенному PowerMill через COM: {progid}"
        except Exception as error:  # noqa: BLE001
            tried.append(f"{progid}: {type(error).__name__}")

    from src.power_mill_link import powermill_running

    if powermill_running() is False:
        return None, ("PowerMill не запущен — живое чтение невозможно. "
                      "Открой PowerMill с проектом и запусти пункт 24 снова.")

    return None, ("PowerMill запущен, но не отвечает как COM-сервер. "
                  "Проверено: " + "; ".join(tried))


# --------------------------------------------------------------------------
# Чтение объектов проекта
# --------------------------------------------------------------------------
def item_name(item) -> str:
    """Имя объекта PowerMill: свойство Name (в разных версиях — name)."""
    for attribute in ("Name", "name"):
        try:
            value = getattr(item, attribute)
        except Exception:  # noqa: BLE001
            continue
        if value:
            return str(value).strip()
    return ""


def iter_collection(collection, limit: int = NAME_LIMIT) -> list:
    """Элементы COM-коллекции: Count/Item, индекс или перебор — что доступно.

    Индексация у Delcam 0-based; если по Count элементов набралось меньше,
    пробуем 1-based — так мы читаем проект на любой версии, ничего не выдумывая.
    """
    items: list = []

    try:
        count = int(collection.Count)
    except Exception:  # noqa: BLE001
        count = None

    seen_ids: set[int] = set()

    def take(index: int) -> bool:
        for getter in (_item_by_method, _item_by_index, _item_by_call):
            try:
                item = getter(collection, index)
            except Exception:  # noqa: BLE001
                continue
            if item is not None and id(item) not in seen_ids:
                seen_ids.add(id(item))
                items.append(item)
                return True
        return False

    if count:
        for index in range(min(count, limit)):
            take(index)
        if len(items) < min(count, limit):        # 0-based не подошёл — пробуем 1-based
            for index in range(1, min(count, limit) + 1):
                take(index)

    if not items:                                  # коллекция без Count — перебор
        try:
            for item in collection:
                items.append(item)
                if len(items) >= limit:
                    break
        except Exception:  # noqa: BLE001
            pass

    return items[:limit]


def _item_by_method(collection, index: int):
    return collection.Item(index)


def _item_by_index(collection, index: int):
    return collection[index]


def _item_by_call(collection, index: int):
    return collection(index)


def names(collection, limit: int = NAME_LIMIT) -> list[str]:
    """Имена объектов коллекции (пустые отбрасываются, дубликаты — нет)."""
    result: list[str] = []
    for item in iter_collection(collection, limit=limit):
        name = item_name(item)
        if name:
            result.append(name)
    return result


class LiveSession:
    """Живой PowerMill: чтение проекта и безопасные команды."""

    def __init__(self, app, source: str = "живой PowerMill (COM)"):
        self.app = app
        self.source = source

    # --- сведения о приложении -------------------------------------------
    @property
    def version(self) -> str:
        for attribute in ("Version", "version"):
            try:
                value = getattr(self.app, attribute)
            except Exception:  # noqa: BLE001
                continue
            if value:
                return str(value)
        return "неизвестна"

    @property
    def project(self):
        """Проект: у PowerMill это `Project` (свойства `ActiveProject` нет)."""
        for attribute in ("Project", "ActiveProject"):
            try:
                project = getattr(self.app, attribute)
            except Exception:  # noqa: BLE001
                continue
            if project is not None:
                return project
        return None

    # --- чтение -----------------------------------------------------------
    def section_names(self, section: str, limit: int = NAME_LIMIT) -> list[str]:
        """Имена объектов раздела (models, tools, toolpaths, ...)."""
        collection_name = COLLECTIONS.get(section)
        project = self.project
        if not collection_name or project is None:
            return []
        try:
            return names(getattr(project, collection_name), limit=limit)
        except Exception:  # noqa: BLE001
            return []

    def counts(self) -> dict[str, int]:
        """Сколько объектов в каждом разделе (для быстрого отчёта)."""
        result: dict[str, int] = {}
        for section in COLLECTIONS:
            try:
                result[section] = len(self.section_names(section, limit=NAME_LIMIT))
            except Exception:  # noqa: BLE001
                result[section] = -1
        return result

    def read_context(self) -> dict:
        """Снимок проекта в том же формате, что разбирает ассистент."""
        import time

        context: dict = {}
        errors: list[str] = []
        for section in COLLECTIONS:
            try:
                found = self.section_names(section)
            except Exception as error:  # noqa: BLE001
                errors.append(f"{section}: {type(error).__name__}: {error}")
                continue
            if found:
                context[section] = found

        context["_total"] = sum(len(v) for k, v in context.items()
                                if not k.startswith("_"))
        context["_parsed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        context["_source"] = f"{self.source}, версия {self.version}"
        if errors:
            context["_errors"] = errors
        return context

    # --- команды ----------------------------------------------------------
    def execute(self, command: str) -> tuple[bool, str]:
        """Выполняет PML-команду в живом PowerMill (DoCommand -> Execute ...).

        Ничего не выдумываем: перебираем методы, которые реально есть в отчёте
        разведки, и возвращаем то, что ответил PowerMill.
        """
        tried: list[str] = []
        for method_name in COMMAND_METHODS:
            method = getattr(self.app, method_name, None)
            if method is None:
                continue
            try:
                # DoCommand/Execute возвращает ответ PowerMill (текст команды или
                # сообщение об ошибке) — он нам нужен для отчётов пункта 33
                result = method(command)
                answer = str(result).strip() if result is not None else ""
                note = f"{method_name}('{command}') -> OK"
                if answer and answer != command:
                    note += f" | ответ: {answer[:300]}"
                if tried:                      # видно, какой способ ругнулся первым
                    note += " | ранее: " + "; ".join(tried)[:300]
                return True, note
            except Exception as error:  # noqa: BLE001
                tried.append(f"{method_name}: {type(error).__name__}: {error}")
        if tried:
            return False, "; ".join(tried)
        return False, "ни DoCommand, ни Execute у объекта нет"

    def save_project(self, path: str | Path) -> tuple[bool, str]:
        """Просит PowerMill сохранить проект (через PML, без догадок об API)."""
        path_text = str(path).replace("/", "\\")
        return self.execute(f'PROJECT SAVE "{path_text}"')


# --------------------------------------------------------------------------
# Готовые сценарии для меню и чата
# --------------------------------------------------------------------------
def connect() -> tuple[LiveSession | None, str]:
    """Присоединяется к запущенному PowerMill и оборачивает в LiveSession."""
    app, message = attach()
    if app is None:
        return None, message
    return LiveSession(app), message


def refresh_context(save: bool = True) -> tuple[dict | None, str]:
    """Читает проект из живого PowerMill и (по желанию) сохраняет снимок.

    Возвращает (контекст, сообщение). Контекст — тот же формат, что у снимка
    через макрос: ассистент использует имена объектов в /ask, /macro, /project.
    """
    session, message = connect()
    if session is None:
        return None, message

    context = session.read_context()
    if not context.get("_total"):
        return context, (message + "\n   В PowerMill сейчас не открыт проект "
                                   "(или в нём нет объектов) — снимок пустой.")

    saved = ""
    if save:
        from src import project_context

        path = project_context.save(context)
        saved = f"\n   Снимок сохранён: {path}"
    return context, message + saved


def status_lines() -> list[str]:
    """Короткий отчёт для чата: версия, проект, сколько объектов."""
    session, message = connect()
    if session is None:
        return [message]
    lines = [message, f"   версия PowerMill: {session.version}"]
    counts = session.counts()
    if not counts:
        lines.append("   объекты проекта прочитать не удалось")
        return lines
    filled = {k: v for k, v in counts.items() if v}
    if not filled:
        lines.append("   проект пуст (или не открыт)")
        return lines
    readable = ", ".join(f"{section}={count}" for section, count in filled.items())
    lines.append(f"   объектов: {readable}")
    return lines


def main() -> int:
    """Проверка вручную: python -m src.pm_com"""
    for line in status_lines():
        print(line)
    context, message = refresh_context()
    if context:
        print()
        from src import project_context

        print(project_context.summary(context))
    return 0 if context else 3


if __name__ == "__main__":
    import sys

    sys.exit(main())
