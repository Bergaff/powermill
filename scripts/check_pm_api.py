"""
Проверка, можно ли подключиться к PowerMill напрямую (пункт 23 меню).

Отвечает на вопрос «пора делать приложение для PowerMill или рано» фактами
с компьютера: что установлено, какие сборки API есть, зарегистрирован ли
PowerMill как COM-сервер, готов ли мост Python.

Плюс кладёт в output макрос PM_PROBE.mac — его запускают внутри PowerMill,
чтобы проверить, что макросы исполняются и что видит PML.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.applog import start_log        # noqa: E402
from src import power_mill_link         # noqa: E402


def main() -> int:
    log = start_log("check_pm_api")
    print(f"Лог этого запуска: {log}")
    print()
    return power_mill_link.main()


if __name__ == "__main__":
    sys.exit(main())
