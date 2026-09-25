"""
NC-ПРОГРАММА ИЗ ТРАЕКТОРИЙ (пункт 36 меню, шаг 3.5).

Создаёт NC-программу в проекте, вкладывает выбранные траектории, ставит номер и
(по желанию) постпроцессор, выводит файл. Команды показывает до выполнения;
в отчёте всегда есть список «что НЕ проверено».

Запуск: scripts\\make_nc.bat (или пункт 36 меню).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import OUTPUT_DIR                          # noqa: E402
from src import pm_com, pm_nc                           # noqa: E402
from src.applog import start_log                        # noqa: E402
from src.console import Wizard, read_line               # noqa: E402

REPORT_FILE = OUTPUT_DIR / "pm_nc_report.txt"


def ask_yes_no(prompt: str) -> bool | None:
    while True:
        text = read_line(prompt)
        if text is None:
            return None
        answer = (text or "").strip().lower()
        if answer in ("да", "д", "yes", "y", "1"):
            return True
        if answer in ("", "нет", "н", "no", "n", "0"):
            return False
        print("  Ответь «да» или «нет» (Enter — нет).")


def live_state() -> tuple[list[str], list[str], str]:
    """(траектории, существующие NC-программы, откуда данные)."""
    session, message = pm_com.connect()
    if session is not None:
        try:
            return (session.section_names("toolpaths"),
                    session.section_names("ncprograms"),
                    f"живой PowerMill (COM), версия {session.version}")
        except Exception as error:                        # noqa: BLE001
            return [], [], f"живой PowerMill ответил ошибкой: {error}"
    return [], [], message


def wait_for_result(before: float, timeout: float = 180.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pm_nc.RESULT_FILE.exists() and pm_nc.RESULT_FILE.stat().st_mtime > before:
            return True
        time.sleep(1.0)
    return False


def main() -> int:
    log = start_log("make_nc")
    print("=" * 64)
    print("  ПУНКТ 36 — NC-ПРОГРАММА (шаг 3.5)")
    print("=" * 64)
    print(f"  Лог: {log}")
    print()
    print("  Соберу NC-программу из траекторий проекта и выведу файл.")
    print("  Постпроцессор — только если укажешь (иначе как в настройках проекта).")
    print()

    toolpaths, programs, source = live_state()
    print(f"  Проект: {source}")
    print(f"    траектории: {', '.join(toolpaths) if toolpaths else '— не видно'}")
    print(f"    NC-программы: {', '.join(programs) if programs else '— нет'}")
    print()

    if "живой" not in source:
        print("  (!) Живого PowerMill нет: он не запущен или не стоит мост pywin32.")
        print("      Запусти PowerMill с открытым проектом (пункт 27 — если нет моста).")
        return 1

    if not toolpaths:
        print("  В проекте нет траекторий — выводить нечего.")
        print("  Сначала пункт 31 (черновая операция), потом пункт 35 (проверки).")
        return 0

    postprocessors = pm_nc.find_postprocessors()
    if postprocessors:
        print("  Найденные постпроцессоры (.pmoptz):")
        for path in postprocessors[:8]:
            print(f"    • {path}")
        if len(postprocessors) > 8:
            print(f"    … ещё {len(postprocessors) - 8}")
    else:
        print("  Постпроцессоры (.pmoptz) не нашлись — можно не указывать:")
        print("  PowerMill возьмёт тот, что стоит в настройках проекта.")
    print()

    steps = [
        ("Имя NC-программы", "как будет в проекте", "PROGRAM"),
        ("Траектории (по порядку)", "через запятую; Enter — все", ", ".join(toolpaths)),
        ("Номер программы", "Enter — 100", "100"),
        ("Постпроцессор (.pmoptz)", "Enter — не задавать", ""),
        ("Выходной файл", "Enter — в папке проекта", ""),
    ]
    wizard = Wizard(steps)
    while not wizard.finished:
        print(wizard.prompt(), end="")
        text = read_line("")
        if text is None:
            return 0
        action = wizard.submit(text)
        if action == "menu":
            print("Ничего не менял.")
            return 0
        if action == "help":
            print("  Enter — значение по умолчанию, «назад» — предыдущий вопрос.")
        print()

    name = (wizard.answers[0] or "PROGRAM").strip() or "PROGRAM"
    chosen = [item.strip() for item in (wizard.answers[1] or "").split(",") if item.strip()]
    if not chosen:
        chosen = list(toolpaths)
    try:
        number = int((wizard.answers[2] or "100").strip())
    except ValueError:
        print("  (!) номер не число, беру 100")
        number = 100
    post_text = (wizard.answers[3] or "").strip().strip('"')
    file_text = (wizard.answers[4] or "").strip().strip('"')

    plan = pm_nc.NcPlan(
        name=name,
        toolpaths=chosen,
        number=number,
        postprocessor=Path(post_text) if post_text else None,
        filename=Path(file_text) if file_text else None,
        overwrite=any(program.lower() == name.lower() for program in programs),
    )

    problems = pm_nc.validate_plan(plan)
    if problems:
        print("  (!) Так выводить нельзя:")
        for problem in problems:
            print(f"      • {problem}")
        return 1

    print("=" * 64)
    print("  ЧТО БУДЕТ СДЕЛАНО (до выполнения)")
    print("=" * 64)
    print("\n".join(pm_nc.preview(plan)))
    if plan.overwrite:
        print()
        print(f"  (!) Программа «{name}» в проекте уже есть — она будет удалена и "
              "создана заново.")
    print()

    answer = ask_yes_no("  Вывести NC-программу сейчас? (да/нет) [нет]: ")
    if not answer:
        print("Ничего не менял.")
        return 0

    macro = pm_nc.write_macro(plan, known_programs=programs)
    print()
    print(f"  Макрос вывода: {macro}")

    session, _message = pm_com.connect()
    if session is None:
        print("  (!) PowerMill пропал — подключение потеряно.")
        return 1

    before = time.time()
    command = f'MACRO "{str(macro).replace(chr(92), "/")}"'
    ok, note = session.execute(command)
    print(f"  PowerMill: {'принял' if ok else 'не принял'} команду запуска")
    if note:
        print(f"    {note}")
    if not ok:
        print("  Запусти макрос вручную: вкладка «Макрос» -> Выполнить -> pm_nc.mac")
        return 1

    print("  Жду отчёт (до 3 минут)…")
    got = wait_for_result(before)
    print()

    steps_result, note = pm_nc.last_result()
    project_folder = pm_nc.project_path(steps_result)
    written = pm_nc.find_written_file(project_folder, before)
    if written is None and plan.filename is not None and Path(plan.filename).exists():
        written = Path(plan.filename)

    body = ["NC-программа (шаг 3.5, пункт 36)", "",
            pm_nc.format_result(steps_result), ""]
    if not got:
        body.append("Отчёт от макроса не появился — макрос остановился или вывод "
                    "ещё идёт. Проверь папку ncprograms проекта.")
    body.extend(pm_nc.not_checked_lines(plan))
    if note:
        body.append("")
        body.append(note)

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text("\n".join(body), encoding="utf-8")

    print(pm_nc.format_result(steps_result))
    print()
    info = pm_nc.written_file_info(written)
    wrote_line = any(step == "write" and status == "ok"
                     for step, status, _detail in steps_result)
    if info is not None:
        file, size = info
        print(f"  ✔ Файл на диске: {file} ({size} байт)")
        body.append(f"Файл на диске: {file} ({size} байт)")
        if not wrote_line:
            note_file = ("Файл на диске есть, а строку «выведен» макрос не дописал: "
                         "скорее всего PowerMill спрашивал подтверждение — вывод при "
                         "этом прошёл. Файл проверь глазами.")
            print(f"  • {note_file}")
            body.append(note_file)
    else:
        where = plan.filename or (project_folder / "ncprograms" if project_folder
                                 else "папка ncprograms проекта")
        print(f"  (!) Файла NC на диске не видно: {where}")
        print("      Проверь путь и постпроцессор (или выведи файл в PowerMill вручную:")
        print("      NC-программа -> правая кнопка -> Вывод).")
        body.append(f"(!) Файла NC на диске не видно: {where} — проверь путь и "
                    "постпроцессор")
    body.append("")
    print()
    print("\n".join(pm_nc.not_checked_lines(plan)))
    print()
    if plan.filename is not None:
        print(f"  Ожидаемый файл NC: {plan.filename}")
    else:
        print("  Файл NC: в папке проекта ncprograms (имя — как у программы)")
    print(f"  Отчёт: {REPORT_FILE} (открывается пунктом 29 меню)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
