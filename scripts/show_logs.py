"""
ПОКАЗАТЬ ЛОГИ последних запусков (output\\logs).

Нужно, когда окно закрылось и непонятно, что произошло: батник всё равно
записывает свою работу в файл. Запуск: scripts\\show_logs.bat
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import OUTPUT_DIR  # noqa: E402

LOG_DIR = OUTPUT_DIR / "logs"


def main() -> int:
    print("=" * 62)
    print("  ЛОГИ ПОСЛЕДНИХ ЗАПУСКОВ")
    print("=" * 62)
    print(f"  Папка: {LOG_DIR}")

    if not LOG_DIR.exists() or not any(LOG_DIR.iterdir()):
        print()
        print("  Логов пока нет — значит, ничего и не запускалось.")
        print("  Начни с разбора справки: пункт 4 меню (или start_parse_help.bat).")
        return 0

    files = sorted(LOG_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    print()
    print("  Файлы (сначала свежие):")
    for f in files[:15]:
        size = f.stat().st_size
        print(f"    {f.name:<24} {size:>8} байт")

    for f in files[:2]:
        print()
        print("-" * 62)
        print(f"  {f.name} — последние 30 строк")
        print("-" * 62)
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as e:
            print(f"  !! не прочитать: {e}")
            continue
        for line in lines[-30:]:
            print("  | " + line)

    print()
    print("=" * 62)
    print("  Если видишь ошибку — пришли этот текст в чат.")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
