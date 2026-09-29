"""
ПРОВЕРКИ ТРАЕКТОРИЙ (пункт 35 меню, шаг 3.4).

Проверяет зарезы и столкновения штатными командами PowerMill и читает его
результат. Команды показывает до выполнения; отчёт складывает в файлы.

Запуск: scripts\\check_toolpaths.bat (или пункт 35 меню).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import OUTPUT_DIR                          # noqa: E402
from src import knowledge                              # noqa: E402
from src import pm_check, pm_com, pm_holder            # noqa: E402
from src.applog import start_log                        # noqa: E402
from src.console import Wizard, read_line               # noqa: E402

REPORT_FILE = OUTPUT_DIR / "pm_check_report.txt"


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


def live_toolpaths() -> tuple[list[str], str]:
    """Имена траекторий из живого PowerMill (или из снимка проекта)."""
    session, message = pm_com.connect()
    if session is not None:
        try:
            return session.section_names("toolpaths"), f"живой PowerMill (COM), версия {session.version}"
        except Exception as error:                        # noqa: BLE001
            return [], f"живой PowerMill ответил ошибкой: {error}"
    return [], message


def live_tools(session) -> list[str]:
    """Имена фрез проекта (пусто — если прочитать не удалось)."""
    if session is None:
        return []
    try:
        return session.section_names("tools")
    except Exception:                                      # noqa: BLE001
        return []


def wait_for_result(before: float, timeout: float = 180.0) -> bool:
    """Ждём файл отчёта: проверки коллизий могут идти долго — до 3 минут."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pm_check.RESULT_FILE.exists() and pm_check.RESULT_FILE.stat().st_mtime > before:
            return True
        time.sleep(1.0)
    return False


def main() -> int:
    log = start_log("check_toolpaths")
    print("=" * 64)
    print("  ПУНКТ 35 — ПРОВЕРКИ ТРАЕКТОРИЙ (шаг 3.4)")
    print("=" * 64)
    print(f"  Лог: {log}")
    print()
    print("  Проверяю штатными средствами PowerMill: зарезы и столкновения.")
    print("  Ничего не меняю в геометрии — только проверки и расчёт, если нужно.")
    print()

    toolpaths, source = live_toolpaths()
    session, _message = pm_com.connect()
    tools = live_tools(session)
    print(f"  Проект: {source}")
    print(f"    траектории: {', '.join(toolpaths) if toolpaths else '— не видно'}")
    print(f"    фрезы: {', '.join(tools) if tools else '— не видно'}")
    print()

    if "живой" not in source:
        print("  (!) Живого PowerMill нет: он не запущен или не стоит мост pywin32.")
        print("      Запусти PowerMill с открытым проектом (пункт 27 — если нет моста).")
        return 1

    if not toolpaths:
        print("  В проекте нет траекторий — проверять нечего.")
        print("  Сначала пункт 31 (черновая операция): он создаст траекторию.")
        return 0

    saved = pm_check.last_result()
    if saved[0]:
        print("  Прошлый прогон проверок:")
        print(pm_check.format_result(saved[0]))
        print()

    saved_spec = pm_holder.load_saved()
    default_tool = tools[0] if len(tools) == 1 else (tools[0] if tools else "")
    default_dia = saved_spec.shank_diameter if saved_spec else 16.0
    steps = [
        ("Траектории для проверки",
         "через запятую; Enter — все из проекта",
         ", ".join(toolpaths)),
        ("Фреза (для державки)",
         "имя фрезы; Enter — " + (default_tool or "как в проекте"), default_tool),
        ("Зазор державки, мм", "Enter — 0.1", "0.1"),
        ("Зазор хвостовика, мм", "Enter — 0.1", "0.1"),
        ("Задать условные хвостовик и патрон?",
         "нужны для проверки столкновений; Enter — да, «нет» — не трогать фрезу",
         "да"),
        ("Диаметр фрезы для условной державки, мм", "Enter — " + f"{default_dia:g}",
         f"{default_dia:g}"),
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

    chosen = [name.strip() for name in (wizard.answers[0] or "").split(",") if name.strip()]
    if not chosen:
        chosen = list(toolpaths)

    def number(value: str, fallback: float) -> float:
        try:
            return float((value or "").replace(",", "."))
        except ValueError:
            print(f"  (!) «{value}» — не число, беру {fallback:g}")
            return fallback

    tool_name = (wizard.answers[1] or "").strip()
    plan = pm_check.CheckPlan(
        toolpaths=chosen,
        holder_clearance=number(wizard.answers[2], 0.1),
        shank_clearance=number(wizard.answers[3], 0.1),
    )
    make_holder = (wizard.answers[4] or "").strip().lower() not in ("нет", "н", "no", "n", "0")
    tool_diameter = number(wizard.answers[5], 16.0)
    spec = pm_holder.load_saved() if saved_spec else pm_holder.HolderSpec.for_tool(tool_diameter)
    if spec is None or abs(spec.shank_diameter - tool_diameter) > 0.001:
        spec = pm_holder.HolderSpec.for_tool(tool_diameter)

    problems = pm_check.validate_plan(plan)
    if problems:
        print("  (!) Проверять нечего:")
        for problem in problems:
            print(f"      • {problem}")
        return 1

    print("=" * 64)
    print("  ЧТО БУДЕТ СДЕЛАНО (до выполнения)")
    print("=" * 64)
    print("\n".join(pm_check.preview(plan)))
    print()
    print("  Проверки PowerMill могут идти долго на сложных траекториях.")
    if make_holder:
        print(f"  Державка: задам фрезе «{tool_name or '?'}» условную "
              f"({spec.describe_ascii()}) — иначе PowerMill не считает столкновения.")
    else:
        print("  Державку не трогаю: если у фрезы её нет, PowerMill откажется")
        print("  считать столкновения — тогда проверю хотя бы зарезы.")
    print()

    answer = ask_yes_no("  Запустить проверки сейчас? (да/нет) [нет]: ")
    if not answer:
        print("Ничего не менял.")
        return 0

    # ---- державка: без неё PowerMill отказывается считать столкновения ----
    holder_report = None
    if session is None:
        session, _message = pm_com.connect()
    if session is None:
        print("  (!) PowerMill пропал — подключение потеряно.")
        return 1

    if make_holder and tool_name:
        print()
        print(f"  Задаю условную державку фрезе «{tool_name}»: {spec.describe_ascii()}")
        print("  (это два цилиндра для проверки столкновений — свою державку "
              "из базы ставь в PowerMill)")
        holder_report = pm_holder.apply_live(session, tool_name, spec, log=print)
        if holder_report.ok:
            pm_holder.save_spec(spec)
            plan.assumed_holder = True
            plan.holder_text = spec.describe()
        else:
            print(holder_report.format())
    elif not tool_name:
        print("  (!) Фреза не названа — державку не задаю.")

    # ---- пробный прогон: PowerMill не должен рушить макрос ----
    print()
    print("  Пробую проверку столкновений на одной траектории (через COM)…")
    probe_ok, probe_note = pm_check.probe_collision(session, chosen[0], plan, log=print)
    if probe_ok:
        print("  Столкновения проверять можно.")
    elif pm_check.collision_refusal(probe_note):
        plan.collision = False
        plan.collision_off_reason = probe_note
        print(f"  (!) Столкновения проверить нечем: {probe_note}")
        print("      Столкновения из проверки убираю — иначе PowerMill остановит "
              "весь макрос и отчёта не будет.")
        print("      Зарезы всё равно проверим.")
    else:
        print(f"  (!) Пробный запуск не прошёл: {probe_note}")
        print("      Оставляю проверку столкновений в макросе, но если PowerMill "
              "остановится — пришли отчёт и трейсы.")

    macro = pm_check.write_macro(plan)
    print()
    print(f"  Макрос проверок: {macro}")

    before = time.time()
    command = f'MACRO "{str(macro).replace(chr(92), "/")}"'
    ok, note = session.execute(command)
    print(f"  PowerMill: {'принял' if ok else 'не принял'} команду запуска")
    if note:
        print(f"    {note}")
    if not ok:
        print("  Запусти макрос вручную: вкладка «Макрос» -> Выполнить -> pm_check.mac")
        return 1

    print("  Жду отчёт (до 3 минут)…")
    got = wait_for_result(before)
    print()

    steps_result, note = pm_check.last_result()
    text = pm_check.format_result(steps_result)
    _all_ok, summary = pm_check.summarize(steps_result)
    body = ["Проверки траекторий (шаг 3.4, пункт 35)", "", text, "", *summary,
            *pm_check.not_checked_lines(plan)]
    if holder_report is not None:
        body += ["", *holder_report.format().splitlines()]
    if not got:
        body.append("")
        body.append("Отчёт от макроса не появился — значит макрос остановился или "
                    "проверки ещё идут.")
        missing = pm_check.missing_traces()
        if missing:
            body.append("Отметок нет у шагов: "
                        + ", ".join(path.name for path in missing)
                        + " — по ним видно, где остановился макрос.")
        body.append("Запусти проверки ещё раз или пришли этот отчёт в чат.")
    if note:
        body.append("")
        body.append(note)

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text("\n".join(body), encoding="utf-8")

    print("\n".join(summary))
    print()
    print(f"  Отчёт: {REPORT_FILE} (открывается пунктом 29 меню)")

    # Урок — если PowerMill нашёл замечания или отчёт не пришёл (иначе не пристаём).
    problems = [line.strip() for line in summary if "✘" in line]
    if not got:
        problems.append("макрос не оставил отчёт — проверки до конца не прошли")
    if problems:
        knowledge.ask_lesson(problems,
                             task="проверки траекторий: " + ", ".join(chosen),
                             source="check_toolpaths", reader=read_line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
