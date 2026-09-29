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
from src import pm_check, pm_com                        # noqa: E402
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
    print(f"  Проект: {source}")
    print(f"    траектории: {', '.join(toolpaths) if toolpaths else '— не видно'}")
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

    steps = [
        ("Траектории для проверки",
         "через запятую; Enter — все из проекта",
         ", ".join(toolpaths)),
        ("Зазор державки, мм", "Enter — 0.1", "0.1"),
        ("Зазор хвостовика, мм", "Enter — 0.1", "0.1"),
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

    plan = pm_check.CheckPlan(
        toolpaths=chosen,
        holder_clearance=number(wizard.answers[1], 0.1),
        shank_clearance=number(wizard.answers[2], 0.1),
    )

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
    print()

    answer = ask_yes_no("  Запустить проверки сейчас? (да/нет) [нет]: ")
    if not answer:
        print("Ничего не менял.")
        return 0

    macro = pm_check.write_macro(plan)
    print()
    print(f"  Макрос проверок: {macro}")

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
        print("  Запусти макрос вручную: вкладка «Макрос» -> Выполнить -> pm_check.mac")
        return 1

    print("  Жду отчёт (до 3 минут)…")
    got = wait_for_result(before)
    print()

    steps_result, note = pm_check.last_result()
    text = pm_check.format_result(steps_result)
    _all_ok, summary = pm_check.summarize(steps_result)
    body = ["Проверки траекторий (шаг 3.4, пункт 35)", "", text, "", *summary]
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
