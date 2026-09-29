"""
ПУНКТ 48 — ЧЕМУ УЧИТЬ АССИСТЕНТА (правила и уроки).

Это то, что называется «обучением»: ассистент не переучивает модель, а читает
твои правила и разобранные случаи. Правила — обычными строками, уроки пишутся
сами после неудачных прогонов (или добавляются тут же руками).

Где лежит: `DATA_ROOT\\knowledge\\rules.md` и `...\\lessons.jsonl`.
В облако эти файлы не отправляются: ответы с ними считает только локальная
модель (Ollama). Если локальной модели нет — ассистент честно скажет, что не
ответит, а не отправит твои данные в интернет.

Запуск: scripts\\knowledge.bat (или пункт 48 меню, кнопка в окне).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import console, knowledge                          # noqa: E402
from src.applog import start_log                            # noqa: E402

BACK_WORDS = ("назад", "меню", "0", "отмена")


def _pause() -> None:
    """Пауза, чтобы экран не убегал: Enter — дальше (как в остальных пунктах)."""
    console.read_line("  Enter — дальше: ")


def open_in_notepad(path: Path, printer=print) -> None:
    """Открывает файл в блокноте (на Linux — просто говорит, где он)."""
    if not path.exists():
        printer(f"  Файла ещё нет: {path}")
        return
    if sys.platform.startswith("win"):
        try:
            subprocess.Popen(["notepad.exe", str(path)])
            printer(f"  Открыл в блокноте: {path}")
            return
        except OSError as error:                            # noqa: BLE001
            printer(f"  Блокнот не открылся ({error}) — файл здесь: {path}")
            return
    printer(f"  Файл знаний: {path}")


def open_folder(path: Path, printer=print) -> None:
    if not path.exists():
        printer(f"  Папки ещё нет: {path}")
        return
    if sys.platform.startswith("win"):
        try:
            subprocess.Popen(["explorer.exe", str(path)])
            printer(f"  Открыл папку: {path}")
            return
        except OSError as error:                            # noqa: BLE001
            printer(f"  Проводник не открылся ({error}). Папка: {path}")
            return
    printer(f"  Папка знаний: {path}")


def show_rules(printer=print) -> None:
    rules = knowledge.load_rules()
    printer()
    if not rules:
        printer("  Правил пока нет.")
        printer(f"  Добавить — пункт 2; файл: {knowledge.RULES_FILE}")
        return
    printer(f"  Правила работы ({len(rules)}):")
    for index, rule in enumerate(rules, 1):
        printer(f"    {index}. {rule}")
    printer()
    printer("  Эти правила подмешиваются в ответы ассистента и в умолчания")
    printer("  пунктов 31/37 — он будет считать «как у тебя».")


def show_lessons(limit: int = 20, printer=print) -> None:
    lessons = knowledge.load_lessons()
    printer()
    if not lessons:
        printer("  Уроков пока нет.")
        printer("  Они появляются сами: если прогон закончился не идеально,")
        printer("  ассистент один раз спросит «что поправил».")
        printer(f"  Файл: {knowledge.LESSONS_FILE}")
        return
    printer(f"  Уроки «что было не так и что помогло» (всего {len(lessons)}, "
            f"последние {min(limit, len(lessons))}):")
    for lesson in lessons[-limit:]:
        printer("")
        printer(lesson.format())
    printer()


def add_rule_dialog(reader=console.read_line, printer=print) -> bool:
    printer()
    printer("  Одно правило — одной строкой. Например:")
    printer("    40Х, фреза D16 z4: S=4500 F=1200, ap=8")
    text = reader("  Правило (Enter — отмена): ")
    if text is None:
        return False
    text = text.strip()
    if not text or text.lower() in BACK_WORDS:
        printer("  Ничего не добавил.")
        return False
    knowledge.add_rule(text)
    printer(f"  Записал: {knowledge.RULES_FILE}")
    printer("  (В облако правило не уходит: такие ответы считает локальная модель.)")
    return True


def remove_rule_dialog(reader=console.read_line, printer=print) -> bool:
    rules = knowledge.load_rules()
    if not rules:
        printer("  Правил нет — удалять нечего.")
        return False
    show_rules(printer=printer)
    text = reader("  Номер правила для удаления (Enter — отмена): ")
    if text is None or not (text or "").strip():
        printer("  Ничего не удалял.")
        return False
    try:
        index = int((text or "").strip())
    except ValueError:
        printer(f"  «{text}» — не номер.")
        return False
    try:
        removed = knowledge.remove_rule(index)
    except IndexError as error:
        printer(f"  {error}")
        return False
    printer(f"  Удалил: {removed}")
    return True


def add_lesson_dialog(reader=console.read_line, printer=print) -> bool:
    printer()
    printer("  Можно записать случай, который стоит помнить. Enter — отмена.")
    task = reader("  Что делали: ")
    if task is None or task.strip().lower() in BACK_WORDS:
        printer("  Ничего не записал.")
        return False
    problem = reader("  Что пошло не так: ")
    if problem is None:
        return False
    fix = reader("  Что помогло: ")
    if fix is None:
        return False
    if not (problem.strip() or fix.strip()):
        printer("  Пусто — не записываю.")
        return False
    knowledge.add_lesson(problem=problem, fix=fix, task=task, source="вручную")
    printer(f"  Записал: {knowledge.LESSONS_FILE}")
    return True


def help_text() -> str:
    return (
        "Как это работает:\n"
        "  • правила и уроки — обычные файлы у тебя на компьютере;\n"
        "  • ассистент читает их перед ответом (см. пометку «Учтены твои знания»);\n"
        "  • ОБЛАКО ЗАПРЕЩЕНО: пока есть знания, ответ считает локальная модель,\n"
        "    иначе ассистент честно откажется отвечать, а не отправит данные наружу;\n"
        "  • модель при этом не переучивается — знания подставляются в ответ."
    )


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    knowledge.ensure_files()

    if "--add" in args:
        index = args.index("--add")
        text = args[index + 1] if index + 1 < len(args) else ""
        if not text.strip():
            print("Пустое правило — не записываю.")
            return 1
        knowledge.add_rule(text)
        print(f"Записал правило: {text}")
        return 0

    if "--show" in args:
        print(knowledge.format_stats())
        print()
        show_rules()
        show_lessons(limit=10)
        return 0

    log = start_log("knowledge")
    print("=" * 64)
    print("  ПУНКТ 48 — ЧЕМУ УЧИТЬ АССИСТЕНТА (правила и уроки)")
    print("=" * 64)
    print(f"  Лог: {log}")
    print()
    print(knowledge.format_stats())
    print()
    print("  Это не переучивание модели: правила и разобранные случаи лежат")
    print("  файлами у тебя и подставляются в ответ. В облако не уходят.")
    print()

    while True:
        print("  1 — показать правила")
        print("  2 — добавить правило")
        print("  3 — удалить правило")
        print("  4 — открыть файл правил в блокноте")
        print("  5 — показать уроки (что было не так и что помогло)")
        print("  6 — добавить урок вручную")
        print("  7 — открыть папку знаний")
        print("  8 — как это работает")
        print("  0 или «назад» — выход")
        print()
        answer = console.read_line("  Выбор: ")
        if answer is None:
            return 0
        choice = (answer or "").strip().lower()
        if choice in ("", "0") or choice in BACK_WORDS:
            print("Ничего не менял." if choice not in ("0", "") else "")
            return 0
        if choice == "1":
            show_rules()
            _pause()
        elif choice == "2":
            add_rule_dialog()
            _pause()
        elif choice == "3":
            remove_rule_dialog()
            _pause()
        elif choice == "4":
            open_in_notepad(knowledge.RULES_FILE)
            _pause()
        elif choice == "5":
            show_lessons()
            _pause()
        elif choice == "6":
            add_lesson_dialog()
            _pause()
        elif choice == "7":
            open_folder(knowledge.KNOWLEDGE_DIR)
            _pause()
        elif choice == "8":
            print()
            print(help_text())
            _pause()
        else:
            print("  Не понял выбор: введи номер от 0 до 8.")


if __name__ == "__main__":
    sys.exit(main())
