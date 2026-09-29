"""
Ответ на запрос из PowerMill (запускается макросом PM_AI_ASK.mac).

Ничего вводить не нужно: запрос уже лежит в output\\pm_request.txt (его записал
макрос), ответ уйдёт в output\\pm_answer.txt и появится в PowerMill после RESUME.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import pm_bridge                        # noqa: E402
from src.applog import start_log                 # noqa: E402


def main() -> int:
    log = start_log("pm_answer")
    print(f"Лог этого запуска: {log}")
    print()

    rc = pm_bridge.handle()
    if rc == 0:
        print()
        print("Закрой это окно и нажми RESUME в PowerMill — ответ появится там.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
