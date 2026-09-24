"""
ШАГ 3.1: записать рассчитанные режимы резания в проект PowerMill (пункт 30 меню).

Что делает по шагам
-------------------
1. Считает S, F, ap, ae по материалу и фрезе (наш же калькулятор, пункт 3).
2. Спрашивает, в какие траектории проекта это записать (по умолчанию — все,
   которые видно в снимке пункта 24 или живьём через COM).
3. **Показывает команды** — что именно будет присвоено и как проверится.
4. Спрашивает подтверждение и путь к папке проекта: перед правкой делается
   копия «Деталь_AI_дата» (оригинал не трогаем — правило безопасности).
5. Пишет макрос `output\\pm_edit.mac` и, если PowerMill открыт, тут же его
   выполняет через COM. Если PowerMill закрыт — говорит запустить макрос
   из ленты «Макрос» и вернуться сюда: пункт прочитает отчёт макроса.
6. Читает `output\\pm_edit_result.txt` и печатает «было → стало»: значения
   читает обратно САМ PowerMill, поэтому отчёт честный.

Почему макрос, а не прямые команды: правка параметров траектории — это
присваивания вида `$tp.SpindleSpeed.Value = 4500`, а это язык макросов, а не
команда PowerMill. Присваивания взяты из реальных макросов форума Autodesk,
второй способ (`EDIT RPM` / `EDIT FRATE`) — из руководства и тех же макросов.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import OUTPUT_DIR                              # noqa: E402
from src import cutting, pm_com, pm_edit, project_context   # noqa: E402
from src.applog import start_log                            # noqa: E402
from src.console import Wizard, read_line                   # noqa: E402

REPORT = OUTPUT_DIR / "pm_edit_report.txt"


def current_toolpaths() -> tuple[list[str], str]:
    """Траектории проекта: живьём (если PowerMill открыт), иначе из снимка."""
    session, _message = pm_com.connect()
    if session is not None:
        names = session.section_names("toolpaths")
        if names:
            return names, "живой PowerMill (COM)"
    context = project_context.load() or {}
    return list(context.get("toolpaths", [])), "снимок проекта (пункт 24)"


def split_names(text: str) -> list[str]:
    """Имена траекторий из строки: через запятую/точку с запятой/пробел."""
    raw = text.replace(";", ",").replace("\n", ",")
    parts = [chunk.strip() for chunk in raw.split(",")]
    return [part for part in parts if part]


def show_last_results() -> None:
    """Показывает прошлый результат макроса, если он есть (без правки проекта)."""
    results, note = pm_edit.last_results()
    if not results:
        return
    print(f"Прошлый запуск макроса правки: {note}")
    print(pm_edit.format_results(results))
    print()


def ask_confirmation() -> bool:
    answer = read_line("Выполнить правку проекта? Напиши ДА (или «назад»): ")
    if answer is None:
        return False
    return answer.strip().lower() in ("да", "yes", "y", "д")


def run_in_live_powermill(macro: Path) -> tuple[bool, str]:
    """Выполняет макрос в уже запущенном PowerMill (DoCommand('MACRO ...'))."""
    session, message = pm_com.connect()
    if session is None:
        return False, message
    command = f'MACRO "{str(macro).replace("/", chr(92))}"'
    ok, answer = session.execute(command)
    return ok, f"{command} -> {answer}"


def wait_for_result(before: float, timeout: float = 20.0) -> bool:
    """Ждёт, пока макрос допишет файл результата."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pm_edit.RESULT_FILE.exists() and pm_edit.RESULT_FILE.stat().st_mtime > before:
            return True
        time.sleep(0.5)
    return False


def main() -> int:
    log = start_log("apply_cutting")
    print("=" * 62)
    print("  ШАГ 3.1 — ЗАПИСЬ РЕЖИМОВ РЕЗАНИЯ В ПРОЕКТ PowerMill")
    print("=" * 62)
    print(f"  Лог: {log}")
    print()
    print("  Считанные S и F пишутся в траектории твоего проекта.")
    print("  Проект меняется ТОЛЬКО после подтверждения и только в тех")
    print("  траекториях, которые ты назовёшь.")
    print()

    toolpaths, source = current_toolpaths()
    if toolpaths:
        print(f"  Траектории ({source}): {', '.join(toolpaths[:12])}"
              + (" …" if len(toolpaths) > 12 else ""))
    else:
        print("  (!) Траекторий не видно: нет ни живого PowerMill, ни снимка.")
        print("      Сначала пункт 24 (снимок проекта) — иначе непонятно, куда писать.")
    print()
    show_last_results()

    steps = [
        ("Материал, фреза, операция",
         "например: Сталь 40Х, фреза D16 z4, черновая",
         "Сталь 40Х, фреза D16 z4, черновая"),
        ("Траектории",
         "имена через запятую; Enter — все видимые",
         ", ".join(toolpaths[:6]) if toolpaths else ""),
        ("Подача врезания, мм/мин",
         "Enter — не менять (оставить как в проекте)", ""),
        ("Папка проекта (для копии)",
         "путь к папке проекта; Enter — копию не делать", ""),
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
            print("  Enter — оставить значение по умолчанию,")
            print("  «назад» — предыдущий вопрос, «меню» — выход.")
        print()

    task, tp_answer, plunge_text, project_folder = (
        (wizard.answers[i] or "").strip() for i in range(4))

    print("Считаю режимы...")
    report, data = cutting.answer(task)
    print()
    print(report)
    print()
    print(f"  → S = {data['S_rpm']} об/мин, F = {data['F_mm_min']} мм/мин, "
          f"ap = {data['ap']} мм, ae = {data['ae']} мм")
    print()

    names = split_names(tp_answer) or toolpaths
    if not names:
        print("(!) Не названо ни одной траектории — писать некуда.")
        print("    Сделай снимок проекта (пункт 24) и запусти пункт 30 снова.")
        return 3

    plunge = None
    if plunge_text:
        try:
            plunge = int(float(plunge_text.replace(",", ".")))
        except ValueError:
            print(f"(!) Подача врезания «{plunge_text}» — не число, оставляю как есть.")

    edits = [pm_edit.SpeedFeed(toolpath=name, spindle=int(data["S_rpm"]),
                               feed=int(data["F_mm_min"]), plunge=plunge)
             for name in names]

    print("=" * 62)
    print("  ЧТО БУДЕТ СДЕЛАНО (команды макроса, до выполнения)")
    print("=" * 62)
    print("\n".join(pm_edit.preview(edits)))
    print()
    print("  ap/ae (глубины) в траекторию НЕ пишу: команда для них известна")
    print("  (EDIT PAR 'Stepdown' / 'Stepover'), но ИМЯ параметра зависит от")
    print("  стратегии (для Model Area Clearance — AreaClearance.ZHeights.Stepdown).")
    print("  Подтвердим имена на твоих стратегиях — и включу запись ap/ae тоже.")
    print()

    macro = pm_edit.write_macro(edits)
    print(f"  Макрос правки: {macro}")
    print()

    if not ask_confirmation():
        print("Отменено. Проект не тронут (макрос можно запустить позже вручную).")
        return 0

    if project_folder:
        try:
            copy = pm_edit.backup_project(project_folder)
            print(f"✔ Копия проекта: {copy}")
        except OSError as error:
            print(f"(!) Копию сделать не удалось: {error}")
            print("    " + pm_edit.project_copy_hint())
            if not ask_confirmation_again():
                print("Отменено (без копии проекта).")
                return 4
    else:
        print("  Копию не делаю — ты выбрал без копии.")
        print("  " + pm_edit.project_copy_hint())
        print()

    before = pm_edit.RESULT_FILE.stat().st_mtime if pm_edit.RESULT_FILE.exists() else 0.0
    ok, message = run_in_live_powermill(macro)
    print()
    lines = [f"Запуск в PowerMill: {message}"]
    if ok:
        print("Макрос отправлен в PowerMill, жду отчёт...")
        got = wait_for_result(before)
        if not got:
            print("(!) Отчёт не появился за 20 секунд. Проверь окно сообщений PowerMill;")
            print("    если макрос ругается — пришли текст, разберёмся.")
    else:
        print(f"(!) Через COM выполнить не вышло: {message}")
        print()
        print("Что сделать вручную (20 секунд):")
        print(f"  1) PowerMill → лента «Макрос» → Выполнить → {macro.name}")
        print(f"  2) выбери файл: {macro}")
        print("  3) появится окно с числом записанных значений")
        print("  4) запусти пункт 30 снова — он покажет «было → стало»")
        lines.append("Автозапуск не удалось — макрос надо выполнить в PowerMill вручную.")

    results, note = pm_edit.last_results()
    print()
    print("=" * 62)
    print("  РЕЗУЛЬТАТ (значения прочитаны обратно из PowerMill)")
    print("=" * 62)
    if results:
        print(pm_edit.format_results(results))
        lines.append(pm_edit.format_results(results))
    else:
        print(f"  Пока ничего: {note}")
        print("  Это нормально, если макрос ещё не запускался в PowerMill.")
    print()

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join([
        "PowerMill AI — отчёт шага 3.1 (запись режимов)",
        f"Время: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Задача: {task}",
        f"Траектории: {', '.join(names)}",
        f"S = {data['S_rpm']}, F = {data['F_mm_min']}, ap = {data['ap']}, ae = {data['ae']}",
        f"Макрос: {macro}",
        "",
        "Что было показано до выполнения:",
        "\n".join(pm_edit.preview(edits)),
        "",
        *lines,
        "",
    ]), encoding="utf-8")
    print(f"💾 Отчёт: {REPORT}  (открыть — пункт 29 меню)")
    print()
    print("Теперь траектории в проекте обновлены. Дальше по плану — шаг 3.2")
    print("(заготовка, границы, плоскости). Проверь в PowerMill: панель")
    print("траектории → подача и обороты.")
    return 0 if results and all(r.ok for r in results) else 0


def ask_confirmation_again() -> bool:
    answer = read_line("Продолжить без копии проекта? Напиши ДА: ")
    if answer is None:
        return False
    return answer.strip().lower() in ("да", "yes", "y", "д")


if __name__ == "__main__":
    sys.exit(main())
