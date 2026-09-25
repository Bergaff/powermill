"""
Запуск окна приложения (пункт 39).

Окно открывается из start_app.bat (двойной щелчок по ярлыку «PowerMill AI»).
Здесь только запуск и понятное сообщение, если окно не открылось.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import app_window                              # noqa: E402


def main() -> int:
    return app_window.main()


if __name__ == "__main__":
    sys.exit(main())
