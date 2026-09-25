"""
ШАГИ 3.2–3.3: собрать черновую операцию в проекте PowerMill (пункт 31 меню).

Что делает
----------
1. Считает режимы (тот же калькулятор, что в пункте 3).
2. Собирает план: инструмент (создать или взять из проекта), заготовка,
   траектория из шаблона стратегии, параметры, режимы, проверки коллизий.
3. **Показывает план и команды** — до выполнения.
4. После подтверждения пишет макрос `output\\pm_operation.mac` и выполняет его:
   сам через COM, если PowerMill открыт, иначе просит запустить из ленты.
5. Читает отчёт макроса (`output\\pm_operation_result.txt`) и печатает по шагам,
   что получилось, а что PowerMill не принял.

Расчёт траектории включается только по отдельному ответу «да» — это самая
долгая операция, и её лучше запускать, когда всё остальное уже проверено.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import OUTPUT_DIR                                   # noqa: E402
from src import cutting, pm_com, pm_edit, pm_operation, project_context  # noqa: E402
from src.applog import start_log                                # noqa: E402
from src.console import Wizard, classify, read_line             # noqa: E402

REPORT = OUTPUT_DIR / "pm_operation_report.txt"


def project_state() -> tuple[list[str], list[str], str]:
    """(модели, инструменты, источник) — из живого PowerMill или из снимка."""
    session, _message = pm_com.connect()
    if session is not None:
        models = session.section_names("models")
        tools = session.section_names("tools")
        if models or tools:
            return models, tools, "живой PowerMill (COM)"
    context = project_context.load() or {}
    return (list(context.get("models", [])), list(context.get("tools", [])),
            "снимок проекта (пункт 24)")


def ask_yes_no(prompt: str, default: bool = False) -> bool | None:
    """Да/нет с возвратом на шаг назад (None = назад)."""
    answer = read_line(prompt)
    if answer is None:
        return None
    action = classify(answer)
    if action in ("back", "menu"):
        return None
    text = answer.strip().lower()
    if not text:
        return default
    return text in ("да", "yes", "y", "д", "1")


def run_in_live_powermill(macro: Path) -> tuple[bool, str]:
    session, message = pm_com.connect()
    if session is None:
        return False, message
    command = f'MACRO "{str(macro).replace("/", chr(92))}"'
    ok, answer = session.execute(command)
    return ok, f"{command} -> {answer}"


def wait_for_result(before: float, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if (pm_operation.RESULT_FILE.exists()
                and pm_operation.RESULT_FILE.stat().st_mtime > before):
            return True
        time.sleep(0.5)
    return False


def main() -> int:
    log = start_log("make_operation")
    print("=" * 64)
    print("  ШАГИ 3.2–3.3 — ЧЕРНОВАЯ ОПЕРАЦИЯ В ПРОЕКТЕ PowerMill")
    print("=" * 64)
    print(f"  Лог: {log}")
    print()
    print("  Что будет: инструмент → заготовка → траектория из шаблона")
    print("  (Model Area Clearance = Offset Area Clearance) → параметры →")
    print("  режимы → проверка коллизий. Расчёт — только если разрешишь.")
    print()

    models, tools, source = project_state()
    print(f"  Данные о проекте: {source}")
    print(f"    модели:      {', '.join(models) if models else '— не видно'}")
    print(f"    инструменты: {', '.join(tools) if tools else '— нет (создадим фрезу)'}")
    print()
    if not models:
        print("  (!) Модель не видна. Открой PowerMill с деталью и запусти")
        print("      пункт 24 (снимок) — тогда ассистент увидит, что обрабатывать.")
        print()
        if not ask_yes_no("  Продолжить всё равно? (да/нет): "):
            return 0

    saved = pm_operation.last_result()
    if saved[0]:
        print("  Прошлый запуск:")
        print(pm_operation.format_result(saved[0]))
        print()

    steps = [
        ("Материал, фреза, операция",
         "например: Сталь 40Х, фреза D16 z4, черновая",
         "Сталь 40Х, фреза D16 z4, черновая"),
        ("Имя траектории", "как будет называться операция в проекте",
         "Chernovaya_D16"),
        ("Инструмент", "имя и диаметр фрезы; Enter — D16",
         "D16_Freza"),
        ("Шаг по XY (ae, мм)", "Enter — из расчёта", ""),
        ("Заглубление (ap, мм)", "Enter — из расчёта", ""),
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

    task, tp_name, tool_text, xy_text, ap_text, project_folder = (
        (wizard.answers[i] or "").strip() for i in range(6))

    print("Считаю режимы...")
    report, data = cutting.answer(task)
    print()
    print(report)
    print()

    tool_name, tool_diameter = tool_text or "D16_Freza", 16.0
    if "D" in tool_name.upper():
        try:
            tail = tool_name.upper().split("D", 1)[1]
            digits = "".join(ch for ch in tail if ch.isdigit() or ch == ".")
            if digits:
                tool_diameter = float(digits)
        except (ValueError, IndexError):
            pass
    if tool_diameter == 16.0 and data.get("D"):
        tool_diameter = float(data["D"])

    def pick(text_value: str, from_calc) -> float | None:
        text_value = (text_value or "").replace(",", ".")
        if not text_value:
            return float(from_calc) if from_calc else None
        try:
            return float(text_value)
        except ValueError:
            print(f"  (!) «{text_value}» — не число, беру из расчёта: {from_calc}")
            return float(from_calc) if from_calc else None

    stepover = pick(xy_text, data.get("ae"))
    stepdown = pick(ap_text, data.get("ap"))

    create_tool = not tools or classify(tool_text) == "input" and not any(
        tool_name.lower() == tool.lower() for tool in tools)

    plan = pm_operation.OperationPlan(
        toolpath_name=tp_name or "Chernovaya_D16",
        tool_name=tool_name or "D16_Freza",
        tool_diameter=tool_diameter,
        create_tool=create_tool,
        stepover=stepover,
        stepdown=stepdown,
        rpm=int(data["S_rpm"]),
        feed=int(data["F_mm_min"]),
        plunge=int(data["F_mm_min"] * 0.6),
        tolerance=0.05,
        thickness=0.0,
    )

    print("=" * 64)
    print("  ПЛАН (до выполнения)")
    print("=" * 64)
    print("\n".join(pm_operation.preview(plan)))
    print()

    answer = ask_yes_no("  Расчёт траектории сделать сразу? (да/нет) [нет]: ")
    if answer is None:
        print("Ничего не менял.")
        return 0
    plan.calculate = answer

    macro = pm_operation.write_macro(plan)
    print()
    print(f"  Макрос операции: {macro}")
    print("  Команды в нём — из рабочих макросов Autodesk; слова создания")
    print("  фрезы перебираются, сработавшее попадёт в отчёт.")
    print()

    if not ask_yes_no("  Выполнить эту правку проекта? (да/нет) [нет]: "):
        print("Отменено. Проект не тронут (макрос можно запустить вручную).")
        return 0

    if project_folder:
        try:
            copy = pm_edit.backup_project(project_folder)
            print(f"✔ Копия проекта: {copy}")
        except OSError as error:
            print(f"(!) Копию сделать не удалось: {error}")
            print("    " + pm_edit.project_copy_hint())
    else:
        print("  Копию не делаю — ты выбрал без копии.")
        print("  " + pm_edit.project_copy_hint())
    print()

    before = (pm_operation.RESULT_FILE.stat().st_mtime
              if pm_operation.RESULT_FILE.exists() else 0.0)
    ok, message = run_in_live_powermill(macro)
    print(f"  Запуск: {message}")
    if ok:
        print("  Жду отчёт макроса...")
        if not wait_for_result(before):
            print("  (!) Отчёт не появился за 30 секунд — посмотри окно сообщений.")
    else:
        print()
        print("  Что сделать вручную:")
        print(f"    1) PowerMill → лента «Макрос» → Выполнить → {macro.name}")
        print(f"       файл: {macro}")
        print("    2) вернись в этот пункт — он покажет отчёт по шагам")

    steps_found, note = pm_operation.last_result()
    print()
    print("=" * 64)
    print("  ЧТО ПОЛУЧИЛОСЬ (по отчёту макроса)")
    print("=" * 64)
    print(pm_operation.format_result(steps_found))
    if not steps_found:
        print(f"  {note}")
    print()

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join([
        "PowerMill AI — отчёт шагов 3.2–3.3 (черновая операция)",
        f"Время: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Задача: {task}",
        f"Траектория: {plan.toolpath_name}; инструмент: {plan.tool_name} "
        f"D{plan.tool_diameter:g}",
        f"Режимы: S={plan.rpm}, F={plan.feed}, врезание={plan.plunge}, "
        f"ae={plan.stepover}, ap={plan.stepdown}, расчёт: {plan.calculate}",
        f"Макрос: {macro}",
        "",
        "План (показывался до выполнения):",
        "\n".join(pm_operation.preview(plan)),
        "",
        "Отчёт макроса:",
        pm_operation.format_result(steps_found),
        "",
    ]), encoding="utf-8")
    print(f"💾 Отчёт: {REPORT}  (открыть — пункт 29 меню)")
    print()
    print("Проверь в PowerMill глазами:")
    print("  • в дереве появилась траектория с этим именем;")
    print("  • в её параметрах — фреза, шаг, заглубление, режимы;")
    print("  • если расчёт был включён — траектория рассчитана (зелёная).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
