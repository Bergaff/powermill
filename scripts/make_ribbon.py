"""
ПАНЕЛЬ «PowerMill AI» НА ЛЕНТЕ PowerMill (пункт 34 меню).

Что делает:
  1. выкладывает макросы-запускатели (`output\\pm_macros\\PM_AI_CHAT.mac` и др.);
  2. находит файл настройки ленты в профиле пользователя;
  3. показывает структуру этого файла (что в нём вообще есть) и что будет
     добавлено — **до** изменений;
  4. после «ДА»: делает копию настройки, добавляет вкладку «PowerMill AI» с
     кнопками, применяет её в запущенном PowerMill
     (`EDIT CUSTOMRIBBON IMPORT` → `APPLY` → `FORM RIBBON TAB UICATEGORY`);
  5. пишет отчёт `output\\pm_ribbon_report.txt`.

Если в файле ленты нет кнопки с макросом (лента ещё не настраивалась) — ничего
не меняем, а объясняем, как добавить кнопку руками (6 кликов, способ Autodesk).

Запуск: scripts\\make_ribbon.bat (или пункт 34 меню).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import pm_macro, pm_ribbon                     # noqa: E402
from src.applog import start_log                        # noqa: E402
from src.console import read_line                       # noqa: E402


def ask_yes_no(prompt: str) -> bool | None:
    while True:
        text = read_line(prompt)
        if text is None:
            return None
        answer = (text or "").strip().lower()
        if answer in ("да", "д", "yes", "y", "1"):
            return True
        if answer in ("", "нет", "н", "no", "n", "0"):
            return False
        print("  Ответь «да» или «нет» (Enter — нет).")


def main() -> int:
    log = start_log("make_ribbon")
    print("=" * 64)
    print("  ПУНКТ 34 — ПАНЕЛЬ «PowerMill AI» НА ЛЕНТЕ")
    print("=" * 64)
    print(f"  Лог: {log}")
    print()
    print("  Кнопки на ленте — это вход в уже готовые сценарии:")
    for label, macro_name, target, hint in pm_ribbon.RIBBON_BUTTONS:
        print(f"    • {label:<20} → {macro_name}  ({hint})")
    print()

    macros = pm_macro.write_all()
    print(f"  Макросы обновлены: {len(macros)} файлов в {pm_macro.MACRO_DIR}")

    ribbon_file = pm_ribbon.find_ribbon_file()
    print(f"  Файл настройки ленты: {ribbon_file or '— не найден'}")
    print()

    if ribbon_file is not None:
        text, _encoding = pm_ribbon._read_xml(ribbon_file)      # noqa: SLF001
        import xml.etree.ElementTree as ET

        try:
            root = ET.fromstring(text)
            print("  Что уже есть в настройке ленты:")
            for line in pm_ribbon.structure_lines(root, limit=25):
                print(line)
        except ET.ParseError as error:
            print(f"  (!) Файл настройки не разобрался как XML: {error}")
            print("      Пришли его в чат — подстроимся под твою версию PowerMill.")
        print()

        title = "PowerMill AI"
        if title in text:
            print(f"  Вкладка «{title}» уже есть — менять ничего не буду.")
            print("  Если кнопок в ней не хватает: удали вкладку руками в")
            print("  File -> Options -> Customise the Ribbon и запусти пункт 34 снова.")
            return 0

        print("  Что будет добавлено:")
        print(f"    вкладка «{title}», группа «Ассистент», "
              f"кнопок: {len(pm_ribbon.RIBBON_BUTTONS)}")
        for label, macro_name, _target, _hint in pm_ribbon.RIBBON_BUTTONS:
            print(f"      {label}  ->  output\\pm_macros\\{macro_name}")
        print()
        print("  Перед изменением сделаю копию файла настройки (откатить — просто")
        print("  вернув копию на место).")
        print()
        answer = ask_yes_no("  Добавить вкладку на ленту сейчас? (да/нет) [нет]: ")
        if answer is None:
            print("Ничего не менял.")
            return 0
        if not answer:
            print("Ничего не менял. Лента — необязательная часть, всё работает")
            print("и через меню батников (start_menu.bat).")
            return 0
    else:
        print("  Настройка ленты ещё не создавалась (файла нет).")
        print("  Открой в PowerMill: File -> Options -> Customise the Ribbon …,")
        print("  закрой окно кнопкой OK (можно ничего не менять) и запусти пункт 34 снова.")
        print()
        print(pm_ribbon.manual_note())
        return 0

    print()
    print("  Делаю…")
    result = pm_ribbon.install(apply_in_powermill=True)
    report = pm_ribbon.save_report(result)
    print()
    print(result.format())
    print()
    print(f"  Отчёт: {report} (открывается пунктом 29 меню)")
    return 0 if result.tab_added else 1


if __name__ == "__main__":
    sys.exit(main())
