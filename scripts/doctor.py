"""
ПРОВЕРКА КОМПЬЮТЕРА (пункт 40) — «готов ли он к работе?».

Запуск: scripts\\doctor.bat, ярлык «PowerMill AI — проверка» или пункт 40 меню.
Ничего не меняет: смотрит и пишет отчёт output\\doctor_report.txt.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import doctor                                  # noqa: E402
from src.applog import start_log                        # noqa: E402


def main() -> int:
    log = start_log("doctor")
    print("=" * 64)
    print("  ПУНКТ 40 — ПРОВЕРКА КОМПЬЮТЕРА")
    print("=" * 64)
    print(f"  Лог: {log}")
    print()

    report = doctor.collect()
    text = report.format()
    print(text)

    path = doctor.save(report)
    print()
    print(f"📝 Отчёт: {path}")
    print("   Этот файл можно целиком прислать в чат — по нему видно, что мешает.")
    print()
    if report.ready:
        print("Готово: компьютер готов к работе.")
        return 0
    print("Не готово: исправь то, что помечено ✘ (советы — под каждой строкой).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
