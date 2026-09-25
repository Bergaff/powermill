"""
Единый список действий «PowerMill AI» (для ленты, плагина и макросов).

Зачем этот файл
---------------
Раньше список кнопок был свой у ленты (пункт 34) и свой у плагина (пункт 38), и
они уже начали расходиться: на ленте не было проверок, NC и «СДЕЛАЙ». Теперь
список **один** — здесь. Из него собираются:

* кнопки вкладки на ленте PowerMill (`src\\pm_ribbon.py`);
* кнопки панели плагина (`src\\pm_plugin.py`);
* макросы-запускатели, которые эти кнопки вызывают.

Что важно и не выдумывается
---------------------------
* `kind="macro"` — кнопка выполняет **наш макрос внутри PowerMill** (например,
  «Ассистент» и «Снимок проекта»). Плагин умеет вызывать макрос прямо в
  PowerMill, поэтому такие кнопки в журнал панели пишут ответ PowerMill.
* `kind="bat"` — сценарий спрашивает технолога (материал, фрезу, припуски),
  поэтому он открывается **отдельным окном**, как двойным щелчком по батнику.
* `kind="inline"` — сценарий без вопросов: его вывод панель показывает в журнале.

Никаких «новых» действий здесь нет: это ровно те сценарии, что уже работают.
Список можно править — обе панели подхватят изменения, потому что читают его.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Имена макросов-запускателей (их пишет пункт 34 в папку макросов PowerMill)
MACRO_DIR_HINT = "output"

GROUP_MACROS = "Внутри PowerMill (макросы)"
GROUP_SCENARIOS = "Сценарии ассистента (отдельное окно)"
GROUP_BROWSER = "В браузере"


@dataclass(frozen=True)
class Action:
    """Кнопка ассистента: одна на все интерфейсы."""

    key: str                                   # короткое имя (для отчётов и тестов)
    label: str                                 # подпись на кнопке
    hint: str                                  # подсказка (tooltip)
    kind: str                                  # "macro" | "bat" | "inline"
    target: str                                # PM_AI_ASK.mac | scripts\make_nc.bat | scripts.make_nc
    arguments: str = ""                        # аргументы для inline-запуска
    bat: str = ""                              # батник для тех же действий на ленте
    launcher: str = ""                         # имя макроса-запускателя (лента)
    group: str = GROUP_SCENARIOS               # группа в панели плагина
    ribbon: bool = True                        # показывать на ленте
    pane: bool = True                          # показывать в панели плагина
    asks: bool = False                         # спрашивает технолога → отдельное окно

    @property
    def is_macro(self) -> bool:
        return self.kind == "macro"

    @property
    def ribbon_target(self) -> str:
        """Что вызывать с ленты: макрос (для macro) или батник."""
        if self.kind == "macro":
            return self.target
        return self.bat or self.target


ACTIONS: tuple[Action, ...] = (
    # --- макросы: выполняются внутри PowerMill ---
    Action(
        key="assistant",
        label="Ассистент (вопрос)",
        hint="Спросить ассистента, не выходя из PowerMill (пункт 28)",
        kind="macro",
        target="PM_AI_ASK.mac",
        launcher="PM_AI_ASK.mac",
        group=GROUP_MACROS,
    ),
    Action(
        key="snapshot",
        label="Снимок проекта",
        hint="Ассистент узнаёт имена объектов проекта (пункт 24)",
        kind="macro",
        target="PM_AI_SNAPSHOT.mac",
        launcher="PM_AI_SNAPSHOT.mac",
        group=GROUP_MACROS,
    ),
    # --- сценарии с вопросами: отдельное окно ---
    Action(
        key="cutting",
        label="Режимы резания",
        hint="Калькулятор S/F по материалу и фрезе (пункт 3)",
        kind="bat",
        target=r"start_cutting.bat",
        bat=r"start_cutting.bat",
        launcher="PM_AI_CUTTING.mac",
        asks=True,
    ),
    Action(
        key="tool",
        label="Фреза в проект",
        hint="Создать фрезу и узнать рабочее слово (пункт 33)",
        kind="bat",
        target=r"scripts\probe_tool.bat",
        bat=r"scripts\probe_tool.bat",
        launcher="PM_AI_TOOL.mac",
        asks=True,
    ),
    Action(
        key="operation",
        label="Черновая операция",
        hint="Инструмент + заготовка + траектория из шаблона (пункт 31)",
        kind="bat",
        target=r"scripts\make_operation.bat",
        bat=r"scripts\make_operation.bat",
        launcher="PM_AI_OPERATION.mac",
        asks=True,
    ),
    Action(
        key="checks",
        label="Проверки (3.4)",
        hint="Зарезы и столкновения штатными командами PowerMill (пункт 35)",
        kind="bat",
        target=r"scripts\check_toolpaths.bat",
        bat=r"scripts\check_toolpaths.bat",
        launcher="PM_AI_CHECK.mac",
        asks=True,
    ),
    Action(
        key="nc",
        label="NC-программа (3.5)",
        hint="Создать NC-программу, вложить траектории и вывести файл (пункт 36)",
        kind="bat",
        target=r"scripts\make_nc.bat",
        bat=r"scripts\make_nc.bat",
        launcher="PM_AI_NC.mac",
        asks=True,
    ),
    Action(
        key="flow",
        label="СДЕЛАЙ (3.6)",
        hint="План → выполнение → проверки → NC одним потоком (пункт 37)",
        kind="bat",
        target=r"scripts\make_flow.bat",
        bat=r"scripts\make_flow.bat",
        launcher="PM_AI_FLOW.mac",
        asks=True,
    ),
    Action(
        key="reports",
        label="Отчёты",
        hint="Открыть сохранённые отчёты в блокноте (пункт 29)",
        kind="bat",
        target=r"scripts\show_reports.bat",
        bat=r"scripts\show_reports.bat",
        launcher="PM_AI_REPORTS.mac",
        asks=True,
    ),
    # --- без вопросов: результат идёт в журнал панели ---
    Action(
        key="chat",
        label="Чат в браузере",
        hint="Интерфейс с прогрессом и отчётами (пункт 32)",
        kind="inline",
        target="scripts.chat_ui",
        arguments="--open",
        bat=r"scripts\chat_ui.bat",
        launcher="PM_AI_CHAT.mac",
        group=GROUP_BROWSER,
    ),
)


# --------------------------------------------------------------------------
# Выборки для интерфейсов
# --------------------------------------------------------------------------
def ribbon_actions() -> tuple[Action, ...]:
    """Кнопки вкладки на ленте (пункт 34)."""
    return tuple(action for action in ACTIONS if action.ribbon)


def pane_actions() -> tuple[Action, ...]:
    """Кнопки панели плагина (пункт 38)."""
    return tuple(action for action in ACTIONS if action.pane)


def ribbon_buttons() -> tuple[tuple[str, str, str, str], ...]:
    """Совместимый вид для ленты: (подпись, макрос-запускатель, цель, подсказка)."""
    return tuple((action.label, action.launcher, action.ribbon_target, action.hint)
                 for action in ribbon_actions())


def pane_groups() -> list[tuple[str, list[Action]]]:
    """Кнопки панели по группам — в том порядке, как они объявлены."""
    groups: list[tuple[str, list[Action]]] = []
    for action in pane_actions():
        for name, items in groups:
            if name == action.group:
                items.append(action)
                break
        else:
            groups.append((action.group, [action]))
    return groups


def by_key(key: str) -> Action | None:
    for action in ACTIONS:
        if action.key == key:
            return action
    return None


def launcher_names() -> tuple[str, ...]:
    """Имена макросов-запускателей (что пункт 34 пишет в папку макросов)."""
    return tuple(action.launcher for action in ribbon_actions() if action.launcher)


def validate() -> list[str]:
    """Проверки самого списка: подписи и ключи не повторяются, цели заполнены."""
    problems: list[str] = []
    for field_name in ("key", "label", "launcher"):
        values = [getattr(action, field_name) for action in ACTIONS
                  if getattr(action, field_name)]
        duplicates = sorted({value for value in values if values.count(value) > 1})
        if duplicates:
            problems.append(f"повторяются {field_name}: {', '.join(duplicates)}")
    for action in ACTIONS:
        if action.kind not in ("macro", "bat", "inline"):
            problems.append(f"{action.key}: неизвестный вид «{action.kind}»")
        if not action.target:
            problems.append(f"{action.key}: не задана цель")
        if action.kind == "macro" and not action.target.lower().endswith(".mac"):
            problems.append(f"{action.key}: макрос должен быть .mac")
        if action.kind == "bat" and not action.asks:
            problems.append(f"{action.key}: батник задаёт вопросы — поставь asks=True")
        if action.kind == "inline" and action.asks:
            problems.append(f"{action.key}: inline-запуск не может спрашивать "
                            "(вопросы ждут ввода, которого в панели нет)")
    return problems
