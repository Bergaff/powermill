"""
Макросы «PowerMill AI» внутри PowerMill (пункт 28 меню).

Создаёт два макроса и кладёт их туда, где PowerMill их видит:

* PM_AI_ASK.mac      — меню «что нужно», вопрос и показ ответа в окне PowerMill;
* PM_AI_SNAPSHOT.mac — снимок проекта (модели, границы, инструменты, траектории).

Запуск в PowerMill: вкладка «Макрос» -> Выполнить -> нужный файл.
Кнопку можно закрепить: правой кнопкой на ленте -> «Настроить ленту» ->
Макрос -> добавить. Подробная инструкция печатается ниже.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import pm_macro                        # noqa: E402
from src.applog import start_log                # noqa: E402


def main() -> int:
    log = start_log("prepare_pm_macros")
    print("=" * 60)
    print("  МАКРОСЫ PowerMill AI (кнопка ассистента внутри PowerMill)")
    print("=" * 60)
    print()
    print(f"Лог: {log}")
    print()

    written = pm_macro.write_all()
    print("Создано:")
    for path in written:
        print(f"  {path}")
    print()

    folders = pm_macro.power_mill_macro_folders()
    copied: list[Path] = []
    failed: list[Path] = []
    if folders:
        print("Копирую в папки макросов PowerMill:")
        for folder in folders:
            for name in ("PM_AI_ASK.mac", "PM_AI_SNAPSHOT.mac"):
                source = pm_macro.MACRO_DIR / name
                if not source.exists():
                    continue
                try:
                    shutil.copy2(source, folder / name)
                    copied.append(folder / name)
                except OSError as error:
                    failed.append(folder / name)
                    print(f"  (!) {folder}: {error}")
        for path in copied:
            print(f"  ✔ {path}")
    else:
        print("Папки макросов PowerMill не нашёл — макросы лежат здесь:")
        print(f"  {pm_macro.MACRO_DIR}")
        print("В PowerMill добавь этот путь: Макрос -> Пути макросов (Macro Paths).")

    if failed:
        print()
        print("Часть копий не удалась (нужны права администратора).")
        print("Ничего страшного: запусти макрос прямо из папки:")
        print(f"  {pm_macro.MACRO_DIR}")

    print()
    print("=" * 60)
    print("  КАК ПОЛЬЗОВАТЬСЯ")
    print("=" * 60)
    print()
    print("В PowerMill: вкладка «Макрос» -> «Выполнить» -> выбери")
    print(f"  {pm_macro.MACRO_DIR}\\PM_AI_ASK.mac")
    print()
    print("  • появится меню: справка / макрос / ошибка / режимы резания;")
    print("  • введи текст вопроса;")
    print("  • ассистент откроет своё окно, посчитает ответ;")
    print("  • нажми RESUME в PowerMill — ответ появится в окне сообщений.")
    print()
    print("Снимок проекта: PM_AI_SNAPSHOT.mac — ассистент сам прочитает объекты")
    print("(модели, границы, инструменты, траектории) и покажет проверки.")
    print()
    print("Чтобы закрепить макрос на кнопке:")
    print("  правой кнопкой по ленте -> «Настроить ленту» -> категория «Макрос»;")
    print("  либо File -> Options -> Macro Paths: добавь папку")
    print(f"  {pm_macro.MACRO_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
