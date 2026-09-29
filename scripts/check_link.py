"""
ПРОВЕРКА СВЯЗИ С POWERMILL (пункт 41).

Отвечает делом: подключается к запущенному PowerMill, читает проект и просит
PowerMill выполнить наш макрос-самопроверку (он записывает файл-отметку).
Обновился файл — значит связь работает в обе стороны.

Запуск: scripts\\check_link.bat или пункт 41 меню (в окне — кнопка «Связь»).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import link_check                              # noqa: E402
from src.applog import start_log                        # noqa: E402


def main() -> int:
    log = start_log("check_link")
    print(f"Лог: {log}")
    print()
    return link_check.main()


if __name__ == "__main__":
    sys.exit(main())
