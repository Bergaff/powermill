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


def install_probe_macro() -> list[Path]:
    """Кладёт PM_PROBE.mac туда, где PowerMill его видит (список «Макрос»)."""
    from config import OUTPUT_DIR
    from src import pm_macro
    import shutil

    source = Path(OUTPUT_DIR) / "PM_PROBE.mac"
    copied: list[Path] = []
    if not source.exists():
        return copied
    for folder in pm_macro.power_mill_macro_folders():
        try:
            shutil.copy2(source, Path(folder) / "PM_PROBE.mac")
            copied.append(Path(folder) / "PM_PROBE.mac")
        except OSError:
            continue
    return copied


def main() -> int:
    log = start_log("check_pm_api")
    print(f"Лог этого запуска: {log}")
    print()
    rc = power_mill_link.main()

    copied = install_probe_macro()
    from config import OUTPUT_DIR
    from src.pm_macro import MACRO_DIR

    print()
    print("Макрос разведки лежит здесь:")
    print(f"  {OUTPUT_DIR / 'PM_PROBE.mac'}")
    print(f"  {MACRO_DIR / 'PM_PROBE.mac'}")
    for path in copied:
        print(f"  ✔ {path}")
    if not copied:
        print("  (в папки PowerMill скопировать не удалось — запусти файл вручную)")

    print()
    print("Важно: макрос САМ записывает снимок проекта в файл")
    print(f"  {OUTPUT_DIR / 'pm_project.txt'}")
    print("Копировать ничего не нужно: после макроса запусти пункт 24 —")
    print("ассистент разберёт этот файл. Ещё быстрее — держи PowerMill открытым:")
    print("тогда пункт 24 читает проект напрямую, вообще без макросов.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
