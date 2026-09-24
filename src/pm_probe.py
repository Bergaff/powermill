"""
Глубокая разведка API PowerMill (внутри уже установленного моста).

Зачем
-----
После установки моста (pywin32 / pythonnet) нужно узнать, как именно ЭТА
версия PowerMill отвечает: какие методы у COM-объекта, как называется активный
проект, как получить списки инструментов и траекторий, как выполнить макрос.

Модуль задаёт эти вопросы программе и печатает ответы. Ничего не угадывается:
если метод не найден — так и написано. Отчёт сохраняется в
`output/pm_api_probe.txt`, его достаточно прислать в чат — по нему пишется
точная интеграция (чтение проекта, заполнение параметров, запуск макросов).
"""
from __future__ import annotations

import time
from pathlib import Path

from config import OUTPUT_DIR

PROBE_FILE = OUTPUT_DIR / "pm_api_probe.txt"

# Что пробуем у COM-объекта, чтобы понять его устройство
MACRO_METHODS = ("ExecuteMacro", "RunMacro", "Execute", "DoCommand", "ExecuteEx",
                 "Run")
PROJECT_ATTRS = ("ActiveProject", "Project", "ActiveDocument", "Document",
                 "ActiveSession", "Session")
COMMAND_METHODS = ("DoCommand", "Execute", "SendCommand", "ExecuteEx",
                   "RunCommand", "Command")


def _safe(callable_or_value, *args):
    """Вызов, который никогда не бросает: возвращает (получилось, значение)."""
    try:
        return True, callable_or_value(*args)
    except Exception as error:  # noqa: BLE001
        return False, f"{type(error).__name__}: {error}"


def _names(obj, limit: int = 120) -> list[str]:
    try:
        return [n for n in dir(obj) if not n.startswith("_")][:limit]
    except Exception:  # noqa: BLE001
        return []


def probe_com_object(app: object) -> list[str]:
    """Задаёт вопросы COM-объекту PowerMill и описывает его."""
    lines: list[str] = []

    lines.append("1) Что умеет COM-объект PowerMill:")
    lines.append("   " + ", ".join(_names(app, 200)))
    try:
        lines.append(f"   тип объекта: {type(app)}")
    except Exception:  # noqa: BLE001
        pass
    lines.append("")

    lines.append("2) Активный проект:")
    project = None
    for attr in PROJECT_ATTRS:
        ok, value = _safe(getattr, app, attr)
        if not ok:
            lines.append(f"   {attr}: ошибка — {value}")
            continue
        if value is None:
            lines.append(f"   {attr}: пусто")
            continue
        lines.append(f"   {attr}: найден ({type(value)})")
        project = value
        break
    if project is None:
        lines.append("   ! Проект не найден. Возможные причины:")
        lines.append("     • PowerMill не запущен — запусти и повтори")
        lines.append("     • COM-сервер стартовал отдельным процессом без проекта")
    lines.append("")

    if project is not None:
        lines.append("3) Что умеет проект:")
        lines.append("   " + ", ".join(_names(project, 200)))
        lines.append("")
        lines.append("4) Коллекции проекта (что реально читается):")
        for attr in ("Models", "ModelCollection", "Tools", "ToolCollection",
                     "Toolpaths", "ToolpathCollection", "Boundaries",
                     "BoundaryCollection", "Workplanes", "Patterns",
                     "StockModels", "NCPrograms", "NcPrograms", "Features",
                     "Machines", "Setups"):
            ok, value = _safe(getattr, project, attr)
            if not ok:
                continue
            if value is None:
                lines.append(f"   {attr}: пусто")
                continue
            count = "?"
            ok_count, value_count = _safe(getattr, value, "Count")
            if ok_count:
                count = value_count
            lines.append(f"   {attr}: доступно, Count={count}")
        lines.append("")

    lines.append("5) Выполнение команд и макросов:")
    for name in MACRO_METHODS + COMMAND_METHODS:
        method = getattr(app, name, None)
        if method is not None:
            lines.append(f"   найден метод: {name}")
    if project is not None:
        for name in COMMAND_METHODS:
            if getattr(project, name, None) is not None:
                lines.append(f"   найден метод у проекта: {name}")
    lines.append("")

    lines.append("6) Пробное выполнение безвредной команды:")
    probe_command = 'PRINT "POWERMILL AI TEST OK"'
    tried = False
    for name, args in (("DoCommand", (probe_command,)),
                       ("Execute", (probe_command,))):
        method = getattr(app, name, None)
        if method is None:
            continue
        ok, result = _safe(method, *args)
        tried = True
        lines.append(f"   {name}({probe_command!r}) -> "
                     + ("OK" if ok else f"ошибка: {result}"))
        break
    if not tried and project is not None:
        for name in COMMAND_METHODS:
            method = getattr(project, name, None)
            if method is None:
                continue
            ok, result = _safe(method, probe_command)
            lines.append(f"   проект.{name}(...) -> "
                         + ("OK" if ok else f"ошибка: {result}"))
            break
    if not tried:
        lines.append("   ! Подходящего метода не нашлось — напишем свой обход.")
    return lines


def probe_dotnet(api: object) -> list[str]:
    """То же для .NET-объекта PMAutomation."""
    lines = ["1) Объект .NET API:", "   " + ", ".join(_names(api, 200)), ""]
    lines.append("2) Активный проект:")
    project = None
    for attr in PROJECT_ATTRS:
        ok, value = _safe(getattr, api, attr)
        if ok and value is not None:
            lines.append(f"   {attr}: найден ({type(value)})")
            project = value
            break
        lines.append(f"   {attr}: {'пусто' if ok else 'ошибка'}")
    lines.append("")
    if project is not None:
        lines.append("3) Что умеет проект:")
        lines.append("   " + ", ".join(_names(project, 200)))
    return lines


def run(verbose: bool = True) -> int:
    """Полная разведка: печатает отчёт и сохраняет файл для отправки в чат."""
    from src import pm_live

    report: list[str] = [
        "=" * 62,
        "  РАЗВЕДКА API PowerMill (для подключения ассистента)",
        f"  Время: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 62, "",
    ]

    available = pm_live.bridges()
    report.append("Мосты Python: " + ", ".join(
        f"{name}={ok}" for name, ok in available.items()))
    from src.power_mill_link import powermill_running

    running = powermill_running()
    report.append("PowerMill запущен: " + ("да" if running else "нет"
                                           if running is False else "неизвестно"))
    assembly = pm_live.find_api_assembly()
    report.append(f"Сборка API: {assembly or 'не найдена'}")
    report.append("")

    if not any(available.values()):
        report.append("(!) Ни pywin32, ни pythonnet не установлены.")
        report.append("    Сначала пункт 27 меню: «Поставить мост к PowerMill».")
        text = "\n".join(report)
        if verbose:
            print(text)
        _save(text)
        return 2

    if running is False:
        report.append("(!) PowerMill не запущен. Запусти его с проектом и повтори —")
        report.append("    иначе COM-сервер стартует пустым, без проекта.")

    api, strategy, message = pm_live.connect()
    report.append(f"Подключение: {strategy} — {message}")
    report.append("")
    if api is None:
        report.append("Подключиться не удалось. Проверь:")
        report.append("  • PowerMill запущен (File -> Open, проект открыт);")
        report.append("  • запущен от имени того же пользователя, что и ассистент;")
        report.append("  • после установки моста окно чата открыто заново.")
        text = "\n".join(report)
        if verbose:
            print(text)
        _save(text)
        return 3

    try:
        if strategy == "com":
            report += probe_com_object(api)
        else:
            report += probe_dotnet(api)
    except Exception as error:  # noqa: BLE001
        report.append(f"(!) Разведка прервалась: {type(error).__name__}: {error}")

    report.append("")
    report.append("=" * 62)
    report.append("  ЧТО ДАЛЬШЕ")
    report.append("=" * 62)
    report.append("Пришли этот файл в чат — по нему ассистент напишет точное")
    report.append("подключение: чтение проекта, заполнение S/F/ap/ae, запуск макросов.")
    text = "\n".join(report)

    if verbose:
        print(text)
    _save(text)
    return 0


def _save(text: str) -> Path:
    PROBE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROBE_FILE.write_text(text, encoding="utf-8")
    print()
    print(f"📝 Отчёт: {PROBE_FILE}")
    print("   Его достаточно прислать в чат целиком.")
    return PROBE_FILE


if __name__ == "__main__":
    import sys

    sys.exit(run())
