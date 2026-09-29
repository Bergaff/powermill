"""
Создание фрезы в живом PowerMill через COM (пункт 33).

Зачем отдельно от пункта 31
---------------------------
В макросе неверная команда останавливает весь макрос: на живом PowerMill 2026
`FILE WRITE "WAIT" TO tf1` дал «недопустимый элемент или команда», и макрос
встал на этой строке. Если бы так же не повезло со словом фрезы
(`CREATE TOOL ; END_MILL`), мы потеряли бы всю операцию целиком и не узнали,
какое слово работает.

Здесь команды уходят в PowerMill **по одной** через COM (`DoCommand`), и после
каждой мы перечитываем список инструментов проекта. Поэтому:

* слово, которое создаёт фрезу, находится без риска потерять остальную работу;
* что именно ответил PowerMill — видно в отчёте построчно;
* найденное слово сохраняется в `output\\pm_tool_word.txt` и подставляется
  первым в макрос пункта 31 — там перебор больше не нужен.

Что НЕ делает: не удаляет инструменты, не трогает существующие. Если фреза с
таким именем уже есть — пункт честно об этом скажет и ничего не создаст.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from config import OUTPUT_DIR
from src import pml_files

# Файл, где мы помним сработавшее слово (его же читает пункт 31)
WORD_FILE = OUTPUT_DIR / "pm_tool_word.txt"

# Порядок проб. Начинаем с того, что реально сработало у тебя, потом — варианты
# из справки и форума Autodesk (подтверждён документацией только DRILL).
DEFAULT_WORDS = ("END_MILL", "ENDMILL", "END MILL")

# Команды настройки фрезы — из макроса Autodesk «altering my macro to create a
# tool from database» (CREATE TOOL ; DRILL, EDIT TOOL ; DIAMETER,
# EDIT TOOL ; NUMBER COMMANDFROMUI, RENAME Tool ; $newTool).
TOOL_COMMANDS = ("DIALOGS MESSAGE OFF", "DIALOGS ERROR OFF")


@dataclass
class ToolStep:
    """Одна отправленная команда и что ответил PowerMill."""

    command: str
    ok: bool
    note: str = ""


@dataclass
class ToolReport:
    """Результат создания фрезы: что делали, чем закончилось."""

    word: str = ""                     # сработавшее слово CREATE TOOL
    tool_name: str = ""                # имя созданной фрезы
    diameter: float = 0.0
    before: list[str] = field(default_factory=list)
    after: list[str] = field(default_factory=list)
    steps: list[ToolStep] = field(default_factory=list)
    ok: bool = False
    message: str = ""

    def format(self) -> str:
        """Отчёт построчно: что отправлено и что ответил PowerMill."""
        lines = ["Создание фрезы в живом PowerMill (пункт 33)", ""]
        lines.append(f"Инструментов было: {', '.join(self.before) or '— нет'}")
        lines.append("")
        for step in self.steps:
            mark = "✔" if step.ok else "✘"
            lines.append(f"{mark} {step.command}")
            if step.note:
                lines.append(f"    {step.note}")
        lines.append("")
        lines.append(f"Инструментов стало: {', '.join(self.after) or '— нет'}")
        lines.append("")
        if self.ok:
            lines.append(f"Слово создания фрезы: {self.word}")
            lines.append(f"Фреза: {self.tool_name} D{self.diameter:g}")
            lines.append("Слово сохранено — пункт 31 подставит его первым "
                         "и перебирать варианты уже не будет.")
        else:
            lines.append(f"Не получилось: {self.message}")
        return "\n".join(lines)


def saved_word() -> str:
    """Слово, которое уже сработало раньше (или пустая строка)."""
    if not WORD_FILE.exists():
        return ""
    try:
        lines = pml_files.read(WORD_FILE).splitlines()
    except OSError:
        return ""
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):      # первая строка-комментарий не в счёт
            return stripped.upper()[:24]
    return ""


def remember_word(word: str) -> Path | None:
    """Запоминает сработавшее слово (им же пользуется пункт 31)."""
    word = (word or "").strip().upper()
    if not word:
        return None
    stamp = f"# сработавшее слово создания фрезы (живой PowerMill)\n{word}\n"
    return pml_files.write(WORD_FILE, stamp)


def word_order(words: tuple[str, ...] | list[str] | None = None) -> list[str]:
    """Порядок проб: сначала то, что уже сработало, потом остальные."""
    order: list[str] = []
    known = saved_word()
    if known:
        order.append(known)
    for word in (words or DEFAULT_WORDS):
        candidate = word.strip().upper()
        if candidate and candidate not in order:
            order.append(candidate)
    return order


def _new_tools(before: list[str], after: list[str]) -> list[str]:
    return [name for name in after if name not in before]


def create_flat_tool(session, name: str = "D16_Freza", diameter: float = 16.0,
                     number: int = 1, words=None, log=None) -> ToolReport:
    """Создаёт плоскую фрезу в живом PowerMill и выясняет рабочее слово.

    `session` — объект с методами `execute(команда) -> (bool, текст)` и
    `section_names("tools") -> [имена]` (это `src.pm_com.LiveSession`; в тестах —
    подставной объект). `log` — функция для строчек прогресса на экран.

    Возвращает ToolReport: он же нужен для отчёта, который читает технолог.
    """
    say = log or (lambda _text: None)
    report = ToolReport(diameter=float(diameter))

    try:
        report.before = list(session.section_names("tools"))
    except Exception as error:                             # noqa: BLE001
        report.message = f"не удалось прочитать список инструментов: {error}"
        return report

    if any(name.lower() == tool.lower() for tool in report.before):
        report.after = list(report.before)
        report.ok = True
        report.tool_name = name
        report.message = (f"фреза «{name}» уже есть в проекте — создавать не нужно, "
                          "пункт 31 возьмёт её как есть")
        say(report.message)
        return report

    # Диалоги PowerMill гасим, чтобы неверная команда не открывала окно ошибки,
    # которое блокирует ответ. В конце вернём как было.
    for command in TOOL_COMMANDS:
        ok, note = session.execute(command)
        report.steps.append(ToolStep(command, ok, note))

    baseline = list(report.before)
    for word in word_order(words):
        command = f"CREATE TOOL ; {word}"
        ok, note = session.execute(command)
        try:
            current = list(session.section_names("tools"))
        except Exception as error:                         # noqa: BLE001
            current = list(baseline)
            note = f"{note} | список инструментов не прочитать: {error}"
        created = _new_tools(baseline, current)
        report.steps.append(ToolStep(command, bool(created), note))
        say(f"   {command}: " + ("сработало" if created else "не подошло"))
        if created:
            report.word = word
            break

    for command in ("DIALOGS ERROR ON", "DIALOGS MESSAGE ON"):
        ok, note = session.execute(command)
        report.steps.append(ToolStep(command, ok, note))

    if not report.word:
        report.after = list(baseline)
        report.message = ("ни одно из слов не создало фрезу: "
                          + ", ".join(word_order(words)))
        return report

    remember_word(report.word)

    created_name = _new_tools(baseline, current)[-1] if current else ""
    for command in (f"EDIT TOOL ; DIAMETER {diameter:g}",
                    f"EDIT TOOL ; NUMBER COMMANDFROMUI {int(number)}",
                    f"RENAME Tool ; '{name}'"):
        ok, note = session.execute(command)
        report.steps.append(ToolStep(command, ok, note))
        say(f"   {command}: " + ("ок" if ok else "ошибка"))

    try:
        report.after = list(session.section_names("tools"))
    except Exception:                                      # noqa: BLE001
        report.after = list(baseline) + [name]

    report.tool_name = name
    report.ok = any(tool.lower() == name.lower() for tool in report.after)
    if report.ok:
        report.message = f"фреза «{name}» создана (слово: {report.word})"
    else:
        report.message = (f"фреза создана как «{created_name or '?'}», "
                          f"переименовать в «{name}» не удалось — проверь в PowerMill")
    return report
