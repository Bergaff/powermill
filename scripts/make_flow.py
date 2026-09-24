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

    plan, lines = pm_flow.build_plan(request)
    print("=" * 64)
    print("  ПЛАН (до выполнения)")
    print("=" * 64)
    print("\n".join(lines))
    print()

    for warning in pm_flow.warnings_for(request):
        print(f"  (!) {warning}")
    if pm_flow.warnings_for(request):
        print()

    if request.tool_from_project:
        print(f"  Фреза «{request.tool_name}» уже есть в проекте — создавать не буду.")
    else:
        print(f"  Фрезы «{request.tool_name}» в проекте нет — создам "
              "(слово создания определит перебор, как в пункте 33).")
    print()

    request.calculate = ask_yes_no("  Считать траекторию сразу? (да/нет) [да]: ") in (None, True)
    request.check_after = ask_yes_no("  Проверки после расчёта (зарезы, столкновения)? "
                                     "(да/нет) [да]: ") in (None, True)
    request.nc_after = ask_yes_no("  Вывести NC-программу после проверок? "
                                 "(да/нет) [нет]: ") is True
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
    macro = pm_flow.operation_macro(plan)
    print(f"  Макрос операции: {macro}")
    before = time.time()
    ok, note = run_macro(macro)
    if not ok:
        report.add("Запуск макроса операции", "fail", note or "PowerMill не принял команду")
        report.warnings.append("Запусти макрос вручную: вкладка «Макрос» -> "
                               "Выполнить -> pm_flow.mac и пришли отчёт.")
        pm_flow.save_report(report)
        print(report.format())
        return 1

    print("  Жду отчёт макроса (до 2 минут)…")
    got = wait_for(pm_operation.RESULT_FILE, before, timeout=120)
    steps_result, _note = pm_operation.last_result()
    print()
    print(pm_operation.format_result(steps_result))
    print()
    for step, status, detail in steps_result:
        report.add(f"Операция: {pm_operation.STEP_TITLES.get(step, step)}", status, detail)

    failed = [step for step, status, _ in steps_result if status == "fail"]
    if not got or failed:
        report.warnings.append("Макрос операции не дошёл до конца или не записал "
                               "отчёт — проверь строки с ✘ и пришли отчёт.")
        pm_flow.save_report(report)
        print()
        print(f"  Отчёт: {pm_flow.save_report(report)} (пункт 29 меню)")
        return 1

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
        nc_plan = pm_nc.NcPlan(
            name=request.nc_name,
            toolpaths=[plan.toolpath_name],
            number=request.nc_number,
            postprocessor=request.postprocessor,
            filename=pm_nc.default_filename(request.project_folder, request.nc_name),
            overwrite=any(p.lower() == request.nc_name.lower() for p in programs),
        )
        nc_macro = pm_nc.write_macro(nc_plan, known_programs=programs)
        before = time.time()
        ok, note = run_macro(nc_macro)
        if not ok:
            report.warnings.append("NC не вывелась: " + (note or "нет ответа"))
        else:
            print("  Жду отчёт вывода NC (до 3 минут)…")
            wait_for(pm_nc.RESULT_FILE, before, timeout=180)
            report.nc_steps, _ = pm_nc.last_result()
            print()
            print(pm_nc.format_result(report.nc_steps))
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
