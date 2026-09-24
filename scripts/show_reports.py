"""
ПОКАЗАТЬ ОТЧЁТЫ (пункт 29 меню).

Нужно, когда вывод пролетел и не успел прочитаться: любой наш батник пишет
отчёт в файл, а этот пункт показывает список файлов и открывает выбранный в
блокноте — можно спокойно прочитать и скопировать.

Запуск: scripts\\show_reports.bat (или пункт 29 меню).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_ROOT, OUTPUT_DIR  # noqa: E402

# Что показываем в списке (по порядку важности для технолога)
KNOWN_REPORTS = (
    ("pm_api_probe.txt", "Разведка API PowerMill (пункт 27)"),
    ("pm_link_report.txt", "Связь с PowerMill: установки, API, COM (пункт 23)"),
    ("pm_macros_report.txt", "Макросы внутри PowerMill (пункт 28)"),
    ("plugin_report.txt", "Каркас плагина PowerMill (пункт 25)"),
    ("project_context.json", "Снимок проекта (пункт 24)"),
    ("pm_edit_report.txt", "Запись режимов резания в проект (пункт 30)"),
    ("pm_edit_result.txt", "Что записалось в проект: было → стало (макрос)"),
    ("pm_operation_report.txt", "Черновая операция: что собралось (пункт 31)"),
    ("pm_operation_result.txt", "Отчёт макроса операции по шагам (STEP)"),
    ("pm_tool_report.txt", "Фреза в проекте: команды и ответы PowerMill (пункт 33)"),
    ("pm_ribbon_report.txt", "Панель «PowerMill AI» на ленте (пункт 34)"),
    ("pm_tool_word.txt", "Слово создания фрезы, которое сработало"),
    ("pm_project.txt", "Снимок проекта от макроса PowerMill (пункт 24)"),
    ("pm_trace_5.txt", "Самопроверка моста: шаг 5 — что ответила внешняя программа"),
    ("pm_trace_4.txt", "Самопроверка моста: шаг 4 — пауза пройдена"),
    ("pm_trace_3.txt", "Самопроверка моста: шаг 3 — запуск .bat отправлен"),
    ("pm_trace_2.txt", "Самопроверка моста: шаг 2 — файл прочитан обратно"),
    ("pm_trace_1.txt", "Самопроверка моста: шаг 1 — файл записан из PowerMill"),
    ("pm_test.txt", "Тестовый файл моста (его пишет PowerMill и .bat)"),
    ("bat_check.txt", "Проверка батников (пункт 26)"),
    ("pml_vocabulary.txt", "Словарь PML из справки"),
    ("OTCHET_DLYA_CHATA.txt", "Отчёт для чата (пункт 13)"),
)


def collect_files() -> list[Path]:
    """Файлы отчётов, которые реально существуют (сначала свежие)."""
    found: list[Path] = []
    for name, _title in KNOWN_REPORTS:
        path = Path(OUTPUT_DIR) / name
        if path.exists():
            found.append(path)

    # плюс любые другие txt/json в output, которые мы не перечислили
    extra: list[Path] = []
    if Path(OUTPUT_DIR).exists():
        for path in Path(OUTPUT_DIR).glob("*"):
            if (path.is_file() and path.suffix.lower() in (".txt", ".json")
                    and path not in found and path.name != "api_key.json"):
                extra.append(path)
    extra.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    found.extend(extra[:10])

    # и свежие логи — по одному на скрипт
    log_dir = Path(OUTPUT_DIR) / "logs"
    if log_dir.exists():
        logs = sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime,
                      reverse=True)[:5]
        found.extend(logs)
    return found


def describe(path: Path) -> str:
    import time

    size = path.stat().st_size
    stamp = time.strftime("%d.%m %H:%M", time.localtime(path.stat().st_mtime))
    title = dict(KNOWN_REPORTS).get(path.name, "")
    suffix = f" — {title}" if title else (" (лог)" if path.suffix == ".log" else "")
    return f"{path.name:<28} {stamp}  {size:>7} б{suffix}"


def open_in_notepad(path: Path) -> bool:
    """Открывает файл в блокноте (Windows). В других системах — не падаем."""
    if os.name != "nt":
        print(f"(не Windows: файл лежит здесь — {path})")
        return False
    try:
        subprocess.Popen(["notepad.exe", str(path)])
        return True
    except Exception as error:  # noqa: BLE001
        print(f"(!) Не удалось открыть блокнот: {error}")
        print(f"    Открой файл вручную: {path}")
        return False


def main() -> int:
    print("=" * 62)
    print("  ОТЧЁТЫ (открываются в блокноте — можно читать и копировать)")
    print("=" * 62)
    print(f"  Папка: {OUTPUT_DIR}")
    print()

    files = collect_files()
    if not files:
        print("  Отчётов пока нет — значит, ничего и не запускалось.")
        print("  Начни с пункта 12 (проверка установки) или 13 (отчёт для чата).")
        print(f"  Данные лежат в: {DATA_ROOT}")
        return 0

    while True:
        print("  Что открыть:")
        for index, path in enumerate(files, start=1):
            print(f"    {index:>2} - {describe(path)}")
        print()
        print("     0 - назад (в меню)")
        print()
        try:
            answer = input("   Выбор: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if answer in ("", "0", "назад", "меню", "q", "exit", "выход"):
            return 0

        if not answer.isdigit() or not 1 <= int(answer) <= len(files):
            print("   (!) Нет такого номера — попробуй ещё раз.")
            print()
            continue

        chosen = files[int(answer) - 1]
        print(f"   Открываю: {chosen.name}")
        open_in_notepad(chosen)
        print()


if __name__ == "__main__":
    sys.exit(main())
