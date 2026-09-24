"""
Поиск примеров макросов на диске (для точной генерации PML).

Autodesk кладёт примеры макросов в папки установки PowerMill, а технолог —
в `data\\macros`. Найденные `.mac` копируются в `data\\macros\\found`, после чего
разбор справки включает их в базу знаний: `/macro` и поиск начинают опираться
на настоящий рабочий синтаксис, а не на догадки модели.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import MACRO_DIR, DATA_DIR          # noqa: E402
from src import macro_index                      # noqa: E402

FOUND_DIR = MACRO_DIR / "found"


def main() -> int:
    print("=" * 58)
    print("  ПОИСК МАКРОСОВ PowerMill НА ДИСКЕ")
    print("  Найденные макросы станут примерами для генерации PML")
    print("=" * 58)

    print("\nСмотрю известные папки PowerMill:")
    for hint in macro_index.INSTALL_HINTS:
        mark = "есть" if Path(hint).exists() else "нет"
        print(f"  [{mark:>4}] {hint}")

    print(f"\nИщу .mac/.pml ...")
    found = macro_index.find_on_disk()
    if not found:
        print("\nМакросов не нашёл — это нормально, если ты их не сохранял.")
        print("Свои макросы складывай в:")
        print(f"  {MACRO_DIR}")
        print("и потом запусти пункт 4 меню (разбор справки) — они попадут в базу.")
        return 0

    FOUND_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    for path in found:
        target = FOUND_DIR / path.name
        if target.exists():
            continue
        try:
            shutil.copy2(path, target)
            copied += 1
        except OSError as error:
            print(f"  (!) не скопировал {path}: {error}")

    print(f"\nНайдено макросов: {len(found)}, скопировано новых: {copied}")
    print(f"Папка: {FOUND_DIR}")
    for path in found[:15]:
        print(f"  {path}")
    if len(found) > 15:
        print(f"  … и ещё {len(found) - 15}")

    pages = macro_index.collect()
    print(f"\nТеперь в базе макросов: {len(pages)}")
    print("\nДальше: пункт 4 меню — разбор справки (макросы попадут в поиск)")

    # подсказка: свои макросы тоже полезны
    if not (DATA_DIR / "macros").exists():
        print(f"\nСовет: свои рабочие макросы складывай в {DATA_DIR / 'macros'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
