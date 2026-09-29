"""
«СКАЗАЛ: ДЕЛАЙ» (пункт 37 меню, шаг 3.6).

Один поток: материал + фреза → план → твоё «ок» → выполнение по шагам
(фреза → заготовка → траектория → параметры → режимы → расчёт) → проверки
(пункт 35) → NC (пункт 36) → отчёт: что сделано, что проверено, что осталось.

Запуск: scripts\\make_flow.bat (или пункт 37 меню).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import OUTPUT_DIR                          # noqa: E402
from src import pml_files                              # noqa: E402
from src import pm_check, pm_com, pm_flow, pm_nc, pm_operation   # noqa: E402
from src.applog import start_log                        # noqa: E402
from src.console import Wizard, read_line               # noqa: E402


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


def live_state() -> tuple[list[str], list[str], list[str], str]:
    """(модели, инструменты, траектории, откуда данные)."""
    session, message = pm_com.connect()
    if session is not None:
        try:
            return (session.section_names("models"),
                    session.section_names("tools"),
                    session.section_names("toolpaths"),
                    f"живой PowerMill (COM), версия {session.version}")
        except Exception as error:                        # noqa: BLE001
            return [], [], [], f"живой PowerMill ответил ошибкой: {error}"
    return [], [], [], message


def wait_for(file: Path, before: float, timeout: float = 180.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if file.exists() and file.stat().st_mtime > before:
            return True
        time.sleep(1.0)
    return False


def run_macro(macro: Path) -> tuple[bool, str]:
    """Отправляет макрос в живой PowerMill."""
    session, _message = pm_com.connect()
    if session is None:
        return False, "PowerMill не отвечает"
    command = f'MACRO "{str(macro).replace(chr(92), "/")}"'
    ok, note = session.execute(command)
    return ok, note


def number(value: str, fallback: float) -> float:
    try:
        return float((value or "").replace(",", "."))
    except ValueError:
        print(f"  (!) «{value}» — не число, беру {fallback:g}")
        return fallback


def main() -> int:
    log = start_log("make_flow")
    print("=" * 64)
    print("  ПУНКТ 37 — «СКАЗАЛ: ДЕЛАЙ» (шаг 3.6)")
    print("=" * 64)
    print(f"  Лог: {log}")
    print()
    print("  Соберу всё в один поток: фреза -> заготовка -> траектория ->")
    print("  параметры -> режимы -> расчёт -> проверки -> NC.")
    print("  Покажу план ДО выполнения и остановлюсь, если что-то не так.")
    print()

    models, tools, toolpaths, source = live_state()
    print(f"  Проект: {source}")
    print(f"    модели:      {', '.join(models) if models else '— не видно'}")
    print(f"    инструменты: {', '.join(tools) if tools else '— нет'}")
    print(f"    траектории:  {', '.join(toolpaths) if toolpaths else '— нет'}")
    print()

    if "живой" not in source:
        print("  (!) Живого PowerMill нет: он не запущен или не стоит мост pywin32.")
        print("      Всё остальное работает, но проект менять некуда.")
        return 1
    if not models:
        print("  (!) Модели в проекте не видно — обрабатывать нечего.")
        print("      Импортируй STEP (Файл -> Импорт) и запусти пункт 37 снова.")
        return 1

    default_tool = tools[-1] if tools else "D16_Freza"
    steps = [
        ("Материал", "например: Сталь 40Х, 12Х18Н10Т, Д16Т", "Сталь 40Х"),
        ("Фреза", f"имя в проекте; есть: {', '.join(tools) if tools else 'нет'}",
         default_tool),
        ("Диаметр фрезы, мм", "Enter — 16", "16"),
        ("Припуск на заготовку по бокам, мм", "Enter — 2", "2"),
        ("Припуск на чистовую (Thickness), мм", "Enter — 0 (в размер)", "0"),
        ("Имя траектории", "как будет в проекте", "Chernovaya_D16"),
        ("Папка проекта для копии", "Enter — без копии", ""),
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

    tool_name = (wizard.answers[1] or default_tool).strip()
    diameter = number(wizard.answers[2], 16.0)
    request = pm_flow.FlowRequest(
        material=(wizard.answers[0] or "Сталь 40Х").strip(),
        tool_name=tool_name,
        tool_diameter=diameter,
        tool_from_project=any(tool.lower() == tool_name.lower() for tool in tools),
        stock_margin_xy=number(wizard.answers[3], 2.0),
        allowance=number(wizard.answers[4], 0.0),
        toolpath_name=(wizard.answers[5] or "Chernovaya_D16").strip(),
        project_folder=Path((wizard.answers[6] or "").strip())
        if (wizard.answers[6] or "").strip() else None,
    )

    # Имя траектории в проекте должно быть свободным: переименование в занятое
    # имя PowerMill не примет, а часть с расчётом идёт после. Ничего не удаляем —
    # берём следующее свободное имя и говорим об этом.
    existing = pm_flow.live_toolpath_names()
    if any(item.strip().lower() == request.toolpath_name.strip().lower()
           for item in existing):
        free = pm_flow.free_toolpath_name(request.toolpath_name, existing)
        print(f"  (!) Траектория «{request.toolpath_name}» в проекте уже есть.")
        print("      Оставить это имя нельзя: PowerMill остановит часть с"
              " переименованием,")
        print("      а операция до неё уже будет сделана. Ничего не удаляю —"
              f" возьму имя «{free}».")
        if not ask_yes_no(f"  Согласен на имя «{free}»? (да/нет) [да]: "):
            print("  Остановлено до изменений — ничего не менял.")
            print("  Другое имя можно назвать в следующем запуске пункта 37.")
            return 0
        request.toolpath_name = free
        print()

    if request.tool_from_project:
        print(f"  Фреза «{request.tool_name}» уже есть в проекте — создавать не буду.")
    else:
        print(f"  Фрезы «{request.tool_name}» в проекте нет — создам "
              "(слово создания определит перебор, как в пункте 33).")
    print()

    answers = [
        ask_yes_no("  Считать траекторию сразу? (да/нет) [да]: "),
        ask_yes_no("  Проверки после расчёта (зарезы, столкновения)? (да/нет) [да]: "),
        ask_yes_no("  Вывести NC-программу после проверок? (да/нет) [нет]: "),
    ]
    if any(answer is None for answer in answers):
        print("Остановлено до изменений — ничего не менял.")
        return 0
    # План собираем ЗАНОВО, уже с ответами человека. Раньше план строился до
    # вопросов: если на «Считать траекторию сразу?» человек отвечал «нет», поток
    # всё равно считал траекторию, а в отчёте при этом стояло «без расчёта».
    plan, lines = pm_flow.plan_with_answers(
        request,
        calculate=answers[0] is not False,
        check_after=answers[1] is not False,
        nc_after=answers[2] is True)
    print("=" * 64)
    print("  ПЛАН (с твоими ответами — ровно это и будет выполняться)")
    print("=" * 64)
    print("\n".join(lines))
    print()

    warnings = pm_flow.warnings_for(request)
    for warning in warnings:
        print(f"  (!) {warning}")
    if warnings:
        print()
    if not plan.calculate:
        print("  Запомни: ты выбрал «без расчёта» — я НЕ буду нажимать CALCULATE,")
        print("  траектория останется не посчитанной (проверки и NC тогда неполные).")
        print()

    print("  Запускаю поток. Проект изменится — работай на копии.")
    print()
    if not ask_yes_no("  Поехали? (да/нет) [нет]: "):
        print("Отменено. Ничего не менял.")
        return 0

    report = pm_flow.FlowReport(request=request)

    copy_path = pm_flow.backup(request.project_folder)
    if copy_path:
        report.add("Копия проекта", "ok", str(copy_path))
        print(f"  ✔ Копия проекта: {copy_path}")

    # ---------------- 1. операция (3.1–3.3) ----------------
    # Выполняем ЧАСТЯМИ, а не одним макросом: PowerMill останавливает макрос на
    # первой неверной строке, и одним файлом мы теряли всю операцию сразу.
    macro = pm_flow.operation_macro(plan)
    print(f"  Макрос операции целиком (на случай ручного запуска): {macro}")
    print("  Выполняю по частям — если на чём-то споткнёмся, остальное уцелеет.")
    print()

    # Перед работой пробуем освободить «залипшие» имена файлов: если прошлый
    # макрос оборвался на ошибке, PowerMill держит файл открытым до конца сессии
    # и отвечает «handle уже используется». Команды идут МОЛЧА (окна PowerMill
    # на это время выключены): имена, которых нет, PowerMill называет «неизвестный
    # handle», и раньше это окно выскакивало человеку как «ошибка».
    session, _message = pm_com.connect()
    if session is not None:
        attempted = pml_files.release_handles(session)
        print(f"  Старые имена файлов освободил молча: {len(attempted)} шт.")
        print("  (Если PowerMill показал окно «неизвестный handle: …» — это про этот")
        print("   шаг. Он безвредный, и теперь такие окна заглушены.)")
        print()

    result_file = pm_flow.new_result_file()
    parts = pm_flow.operation_parts(plan, result_file=result_file)
    print(f"  Отчёт макроса этого запуска: {result_file}")
    print()
    steps_result: list[tuple[str, str, str]] = []
    for index, (part, part_path) in enumerate(parts, start=1):
        print(f"  [{index}/{len(parts)}] {part.title} …")
        if part.key == "toolpath":
            print("        Если PowerMill откроет окно выбора шаблона — выбери")
            print("        3D-Area-Clearance -> Model-Area-Clearance и «Применить».")
        before = time.time()
        ok, note = run_macro(part_path)
        if not ok:
            report.add(f"Операция: {part.title}", "fail",
                       note or "PowerMill не принял команду")
            report.warnings.append("Часть не запустилась. Отчёт макроса операции "
                                   "и этот файл можно прислать в чат.")
            print()
            print(f"  ✘ {part.title}: PowerMill не принял команду ({note})")
            print(f"  Файл части: {part_path}")
            print(f"  Отчёт: {pm_flow.save_report(report)} (пункт 29 меню)")
            return 1
        if not pm_flow.wait_for_part(part, before, result_file):
            if part.verify:
                # Часть-проверка перед опасным шагом (сейчас это заготовка):
                # если она не прочиталась, расчёт почти наверняка упадёт с
                # «заготовка не определена» — объясняем и спрашиваем.
                report.add(f"Операция: {part.title}", "fail",
                           "не удалось прочитать заготовку — похоже, она не определена")
                report.warnings.append(
                    "Заготовка не определилась. В PowerMill: Домой -> Заготовка ->"
                    " «Вычислить» -> «Принять», потом запусти пункт 37 заново.")
                print()
                print(f"  ✘ {part.title}: заготовку прочитать не удалось.")
                print("     Это значит, что она НЕ определена — расчёт упадёт с тем же")
                print("     «заготовка не определена или содержит неподходящие значения».")
                print("     Что сделать в PowerMill руками (полминуты):")
                print("       Домой -> Заготовка -> «Вычислить» -> «Принять».")
                print("     Потом запусти пункт 37 заново — он увидит готовую заготовку.")
                print(f"  Файл части: {part_path}")
                print(f"  Отчёт: {pm_flow.save_report(report)} (пункт 29 меню)")
                if not ask_yes_no("  Попробовать расчёт всё равно? (да/нет) [нет]: "):
                    return 0
                print("  Хорошо, продолжаю — расчёт может не пройти.")
                print()
                steps_result, _note = pm_operation.last_result(result_file)
                for step, status, detail in steps_result:
                    report.add(f"Операция: {pm_operation.STEP_TITLES.get(step, step)}",
                               status, detail)
                continue
            report.add(f"Операция: {part.title}", "fail",
                       "PowerMill не дошёл до конца этой части")
            report.warnings.append(
                f"Остановились на части «{part.title}» — посмотри окно сообщений "
                f"PowerMill (там строка с ошибкой) и пришли отчёт. Файл этой части: "
                f"{part_path}")
            print()
            print(pm_operation.format_result(pm_operation.last_result(result_file)[0]))
            print()
            print(f"  ✘ PowerMill не дошёл до конца части «{part.title}».")
            print("     Смотри окно сообщений самого PowerMill: там строка с ошибкой.")
            print(f"     Файл этой части: {part_path}")
            if part.reads:
                print("     Это часть-проверка (для отчёта): работа в проекте уже")
                print("     сделана, можно идти дальше — напиши мне, дочитаем вместе.")
            print(f"  Отчёт: {pm_flow.save_report(report)} (пункт 29 меню)")
            return 1
        # Часть может сама написать «fail» (например, ни одно слово создания
        # инструмента не подошло) — тогда дальше идти нет смысла.
        failure = pm_flow.part_failure(part, result_file)
        if failure:
            report.add(f"Операция: {part.title}", "fail", failure)
            report.warnings.append(f"Часть «{part.title}» сообщила об ошибке. "
                                   "Файл части и отчёт можно прислать в чат.")
            print(f"      ✘ {failure}")
            print(f"  Файл части: {part_path}")
            print(f"  Отчёт: {pm_flow.save_report(report)} (пункт 29 меню)")
            return 1
        for line in pm_operation.format_result(
                pm_flow.part_steps(part, result_file)).splitlines():
            print("      " + line.strip())
    steps_result, _note = pm_operation.last_result(result_file)
    print()
    print("  Итог по операции — по шагам выше. Что не прошло, будет видно в отчёте.")
    print()
    for step, status, detail in steps_result:
        report.add(f"Операция: {pm_operation.STEP_TITLES.get(step, step)}", status, detail)
    report.warnings.append(f"Отчёт макроса этого запуска: {result_file}")

    # ---------------- 2. проверки (3.4) ----------------
    if request.check_after and request.calculate:
        print("=" * 64)
        print("  ПРОВЕРКИ (зарезы, столкновения)")
        print("=" * 64)
        check_plan = pm_check.CheckPlan(toolpaths=[plan.toolpath_name], recalc=False)
        check_macro = pm_check.write_macro(check_plan)
        before = time.time()
        ok, note = run_macro(check_macro)
        if not ok:
            report.warnings.append("Проверки не запустились: " + (note or "нет ответа"))
        else:
            print("  Жду отчёт проверок (до 3 минут)…")
            wait_for(pm_check.RESULT_FILE, before, timeout=180)
            report.check_steps, _ = pm_check.last_result()
            ok_checks, summary = pm_check.summarize(report.check_steps)
            print()
            print("\n".join(summary))
            for step, status, detail in report.check_steps:
                report.add(f"Проверки: {pm_check.STEP_TITLES.get(step, step)}", status, detail)
            if not ok_checks:
                report.warnings.append("PowerMill нашёл замечания при проверке — "
                                       "смотри блок проверок в отчёте.")
        print()
    elif request.check_after and not request.calculate:
        report.warnings.append("Проверки пропущены: траектория не посчитана.")
        report.add("Проверки", "skip", "траектория не посчитана")

    # ---------------- 3. NC (3.5) ----------------
    if request.nc_after:
        print("=" * 64)
        print("  NC-ПРОГРАММА")
        print("=" * 64)
        programs = []
        session, _message = pm_com.connect()
        if session is not None:
            try:
                programs = session.section_names("ncprograms")
            except Exception:                              # noqa: BLE001
                programs = []
        # Постпроцессор обязателен: без него PowerMill отказывается писать NC
        # («должен быть задан файл постпроцессора»), и в новом проекте его нет.
        post = request.postprocessor or pm_nc.saved_post()
        if post is not None and not Path(post).exists():
            print(f"  (!) Постпроцессора нет на диске: {post}")
            post = None
        if post is None:
            found = pm_nc.find_postprocessors()
            print("  (!) Постпроцессор не задан, а без него PowerMill файл не пишет.")
            if found:
                print("      Нашёл на компьютере (можно скопировать путь):")
                for path in found[:8]:
                    print(f"        • {path}")
            else:
                print("      Не нашёл .pmoptz ни в папке данных, ни в установке")
                print("      PowerMill (file\\proc), ни в утилите постпроцессоров.")
            print(f"      Путь можно вписать в {pm_nc.POST_FILE} — и запустить заново.")
            text = read_line("  Путь к файлу постпроцессора (.pmoptz),"
                             " Enter — пропустить NC: ")
            if text is not None and text.strip():
                post = Path(text.strip().strip('"'))
                if post.exists():
                    pm_nc.save_post(post)
                    print(f"  Запомнил постпроцессор: {pm_nc.POST_FILE}")
                else:
                    print(f"  (!) Такого файла нет: {post}")
                    post = None
        if post is None:
            print("  NC-программа пропущена: без файла постпроцессора PowerMill её не выведет.")
            print("  (Пункт 36 умеет найти постпроцессоры и запомнить выбранный.)")
            report.warnings.append("NC пропущена: не задан постпроцессор — PowerMill без "
                                   "него файл не пишет")
            report.add("NC-программа", "skip", "не задан постпроцессор")
            print()

        nc_plan = None if post is None else pm_nc.NcPlan(
            name=request.nc_name,
            toolpaths=[plan.toolpath_name],
            number=request.nc_number,
            postprocessor=post,
            filename=pm_nc.default_filename(request.project_folder, request.nc_name),
            overwrite=any(p.lower() == request.nc_name.lower() for p in programs),
        )
        nc_macro = None if nc_plan is None else pm_nc.write_macro(nc_plan,
                                                                  known_programs=programs)
        before = time.time()
        ok, note = (False, "нет постпроцессора") if nc_macro is None else run_macro(nc_macro)
        if nc_macro is None:
            pass                                  # уже объяснили и записали в отчёт
        elif not ok:
            report.warnings.append("NC не вывелась: " + (note or "нет ответа"))
        else:
            print("  Жду отчёт вывода NC (до 3 минут)…")
            wait_for(pm_nc.RESULT_FILE, before, timeout=180)
            report.nc_steps, _ = pm_nc.last_result()
            written = pm_nc.find_written_file(pm_nc.project_path(report.nc_steps),
                                              before)
            if written is None and Path(nc_plan.filename).exists():
                written = Path(nc_plan.filename)
            print()
            print(pm_nc.format_result(report.nc_steps))
            info = pm_nc.written_file_info(written)
            wrote_line = any(step == "write" and status == "ok"
                             for step, status, _detail in report.nc_steps)
            if info is not None:
                file, size = info
                print(f"  ✔ Файл на диске: {file} ({size} байт)")
                report.add("NC: файл на диске", "ok", f"{file} ({size} байт)")
                if not wrote_line:
                    report.add("NC: подтверждение вывода", "skip",
                               "файл на диске есть, строку «выведен» макрос не дописал "
                               "(PowerMill спрашивал подтверждение)")
            else:
                print("  (!) Файла NC на диске не видно — проверь путь и постпроцессор")
                report.add("NC: файл на диске", "fail",
                           "файл не найден — проверь путь и постпроцессор")
                report.warnings.append("NC-файла на диске не видно: проверь путь "
                                       "вывода и постпроцессор.")
            print("\n".join(pm_nc.not_checked_lines(nc_plan)))
            for step, status, detail in report.nc_steps:
                report.add(f"NC: {pm_nc.STEP_TITLES.get(step, step)}", status, detail)
        print()

    report.finished = True
    path = pm_flow.save_report(report)
    print("=" * 64)
    print("  ИТОГ")
    print("=" * 64)
    print(report.format())
    print()
    print(f"  Отчёт: {path} (открывается пунктом 29 меню)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
