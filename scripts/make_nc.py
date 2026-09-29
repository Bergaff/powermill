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
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import OUTPUT_DIR                          # noqa: E402
from src import pm_com, pm_nc                           # noqa: E402
from src.applog import start_log                        # noqa: E402
from src import console
from src.console import Wizard, read_line               # noqa: E402

REPORT_FILE = OUTPUT_DIR / "pm_nc_report.txt"


def ask_yes_no(prompt: str) -> bool | None:
    while True:
        text = read_line(prompt)
        if text is None:
            return None
        answer = (text or "").strip().lower()
        if answer in ("да", "д", "yes", "y", "1"):
            print()
            return True
        if answer in ("", "нет", "н", "no", "n", "0"):
            print()
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

    saved_post = pm_nc.saved_post()
    if saved_post is not None:
        print(f"  Запомненный постпроцессор: {saved_post}")
        if not Path(saved_post).exists():
            print("    (!) этого файла на диске нет — возьми другой или впиши путь заново")
        print(f"    (файл {pm_nc.POST_FILE} — можно править руками)")
    postprocessors = pm_nc.find_postprocessors()
    if postprocessors:
        print("  Найденные постпроцессоры (.pmoptz):")
        hints = pm_nc.post_hints(postprocessors[:12])
        for index, (path, hint) in enumerate(zip(postprocessors[:12], hints), start=1):
            print(f"    {index}. {path}")
            if hint:
                print(f"       {hint}")
        if len(postprocessors) > 12:
            print(f"    … ещё {len(postprocessors) - 12}")
        print("    (номер можно вписать в ответ про постпроцессор — или путь)")
        print("    Если стойку не знаешь — начни с Fanuc.pmoptz: он подходит")
        print("    большинству стоек; точный пост подбирает технолог станка.")
    else:
        print("  Постпроцессоры (.pmoptz) не нашлись.")
        print("  Искал: папку данных, установку PowerMill (file\\proc) и утилиту")
        print("  «Manufacturing Post Processor Utility» в Документах (там Generic-посты).")
    print()

    steps = [
        ("Имя NC-программы", "как будет в проекте", "PROGRAM"),
        ("Траектории (по порядку)", "через запятую; Enter — все", ", ".join(toolpaths)),
        ("Номер программы", "Enter — 100", "100"),
        ("Постпроцессор (.pmoptz)",
         "Enter — не задавать" if saved_post is None
         else f"Enter — запомненный: {saved_post}",
         str(saved_post) if saved_post is not None else ""),
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

    if plan.postprocessor is None and postprocessors:
        text = read_line("  Номер из списка или путь к .pmoptz, Enter — не задавать: ")
        if text is not None and text.strip():
            number = console.pick_index(text, len(postprocessors))
            chosen = postprocessors[number] if number is not None else Path(
                text.strip().strip('"'))
            if chosen.exists():
                plan.postprocessor = chosen
            else:
                print(f"  (!) Такого файла нет: {chosen}")

    if plan.postprocessor is None:
        print("  (!) Постпроцессор не задан. Если в проекте его тоже нет (новый проект),")
        print("      PowerMill откажется писать файл: «должен быть задан файл")
        print("      постпроцессора». Возьми путь из списка выше или впиши его в")
        print(f"      {pm_nc.POST_FILE} — и запусти пункт 36 заново.")
        print()
        if not ask_yes_no("  Продолжить без постпроцессора? (да/нет) [нет]: "):
            print("Ничего не менял.")
            return 0

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

    if plan.postprocessor is not None and Path(plan.postprocessor).exists():
        answer = read_line("  Запомнить этот постпроцессор для следующих запусков?"
                           " (да/нет) [да]: ")
        if answer is not None and answer.strip().lower() not in (
                "нет", "н", "no", "n", "0"):
            pm_nc.save_post(plan.postprocessor)
            print(f"  Запомнил: {pm_nc.POST_FILE}")

    session, _message = pm_com.connect()
    if session is None:
        print("  (!) PowerMill пропал — подключение потеряно.")
        return 1

    # ---- попытки: пост может не встать с первого способа — пробуем следующие ----
    # Так уже было на живом PowerMill: короткая команда TAPEOPTIONS прошла без
    # ошибки, а вывод упал с «должен быть задан файл постпроцессора».
    attempts = pm_nc.attempt_order() if plan.postprocessor is not None else [None]
    steps_result: list[tuple[str, str, str]] = []
    note = ""
    written: Path | None = None
    project_folder: Path | None = None
    used_form = None
    tried: list[str] = []

    for index, form in enumerate(attempts):
        title = form.title if form is not None else "без постпроцессора"
        print()
        print(f"  Попытка {index + 1} из {len(attempts)}: {title}")
        if index > 0:
            print("    (программу с этим именем пересоздам — она пустая, "
                  "осталась от прошлой попытки)")
        attempt_plan = replace(plan, overwrite=plan.overwrite or index > 0)
        macro = pm_nc.write_macro(attempt_plan, known_programs=programs, form=form)
        print(f"    макрос: {macro}")
        before = time.time()
        ok, note = session.execute(f'MACRO "{str(macro).replace(chr(92), "/")}"')
        if not ok:
            print(f"    PowerMill не принял команду запуска: {note}")
            tried.append(f"{index + 1}. {title} — макрос не запустился")
            continue
        print("    жду отчёт (до 3 минут)…")
        got = wait_for_result(before)
        steps_result, note = pm_nc.last_result()
        project_folder = pm_nc.project_path(steps_result) or project_folder

        written = None
        if attempt_plan.filename is not None:
            guess = Path(attempt_plan.filename)
            try:
                if guess.exists() and guess.stat().st_mtime >= before - 2:
                    written = guess
            except OSError:
                written = None
        if written is None:
            written = pm_nc.find_written_file(project_folder, before)

        wrote_line = any(step == "write" and status == "ok"
                         for step, status, _detail in steps_result)
        if written is not None:
            used_form = form
            tried.append(f"{index + 1}. {title} — файл записан")
            break
        if not got:
            tried.append(f"{index + 1}. {title} — макрос остановился (отчёта нет)")
        elif wrote_line:
            tried.append(f"{index + 1}. {title} — макрос отчитался, но файла нет")
        else:
            tried.append(f"{index + 1}. {title} — вывод не прошёл")
        if index + 1 < len(attempts):
            print("    файла NC не видно — пробую следующий способ")

    if used_form is not None and plan.postprocessor is not None:
        pm_nc.remember_form(used_form)
        print()
        print(f"  ✔ Способ установки поста запомнен: {used_form.key}")

    wrote_line = any(step == "write" and status == "ok"
                     for step, status, _detail in steps_result)
    info = pm_nc.written_file_info(written)

    body = ["NC-программа (шаг 3.5, пункт 36)", "",
            pm_nc.format_result(steps_result), ""]
    if tried:
        body.append("Попытки установки постпроцессора:")
        body.extend(f"  {item}" for item in tried)
        body.append("")
    body.extend(pm_nc.not_checked_lines(plan))
    if note:
        body.append("")
        body.append(note)

    print()
    print(pm_nc.format_result(steps_result))
    print()
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
        print(f"  (!) Файла NC на диске нет: {where}")
        print("      Ни один способ установки поста не дал файла. Что делать:")
        print("      1) в PowerMill задай пост сам: NC-программа -> постпроцессор -> "
              "выбрать .pmoptz -> ОК;")
        print("         после этого запусти пункт 36 ещё раз;")
        print("      2) или запиши макрос руками: в PowerMill включи запись макроса, "
              "выбери пост")
        print("         в NC-программе, останови запись и пришли файл — вставим твои "
              "строки")
        print("         как ещё один способ (сейчас пробовали: "
              + ", ".join(form.key for form in attempts if form is not None) + ").")
        body.append(f"(!) Файла NC на диске нет: {where} — ни один способ установки "
                    "поста не сработал, проверь постпроцессор")

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text("\n".join(body), encoding="utf-8")

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
