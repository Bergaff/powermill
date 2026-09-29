"""
СОЗДАТЬ ФРЕЗУ В ПРОЕКТЕ И ВЫЯСНИТЬ РАБОЧЕЕ СЛОВО (пункт 33 меню).

Зачем это до пункта 31: в макросе неверная команда останавливает весь макрос, и
мы потеряли бы всю черновую операцию. Здесь команды уходят в живой PowerMill по
одной, после каждой читается список инструментов — поэтому видно, какое слово
создаёт фрезу, и ничего не теряется.

Что делает по шагам:
  1. читает живой проект (какие модели и инструменты уже есть);
  2. спрашивает имя и диаметр фрезы, показывает команды **до** выполнения;
  3. после «ДА» создаёт фрезу (перебор слов END_MILL / ENDMILL / END MILL,
     начиная с того, что сработало в прошлый раз), ставит диаметр, номер и имя;
  4. пишет отчёт `output\\pm_tool_report.txt` и запоминает слово в
     `output\\pm_tool_word.txt` — пункт 31 подставит его первым.

Проект меняется только после подтверждения. Если фреза с таким именем уже есть,
пункт ничего не создаёт, а честно говорит об этом.

Запуск: scripts\\probe_tool.bat (или пункт 33 меню).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import OUTPUT_DIR                          # noqa: E402
from src import pm_com, pm_tool                         # noqa: E402
from src.applog import start_log                        # noqa: E402
from src.console import Wizard, read_line               # noqa: E402

REPORT_FILE = OUTPUT_DIR / "pm_tool_report.txt"


def ask_yes_no(prompt: str) -> bool | None:
    """«да» — True, «нет»/Enter — False, «меню»/«назад» — None (не делаем ничего)."""
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


def live_state() -> tuple[list[str], list[str], str]:
    """(модели, инструменты, откуда данные) — живой проект или снимок."""
    session, message = pm_com.connect()
    if session is not None:
        try:
            models = session.section_names("models")
            tools = session.section_names("tools")
            return models, tools, f"живой PowerMill (COM), версия {session.version}"
        except Exception as error:                          # noqa: BLE001
            return [], [], f"живой PowerMill ответил ошибкой: {error}"
    return [], [], message


def main() -> int:
    log = start_log("probe_tool")
    print("=" * 64)
    print("  ПУНКТ 33 — ФРЕЗА В ПРОЕКТЕ PowerMill (и рабочее слово)")
    print("=" * 64)
    print(f"  Лог: {log}")
    print()

    models, tools, source = live_state()
    print(f"  Проект: {source}")
    print(f"    модели:      {', '.join(models) if models else '— не видно'}")
    print(f"    инструменты: {', '.join(tools) if tools else '— нет'}")
    print()

    if "живой" not in source:
        print("  (!) Живого PowerMill нет: он не запущен или не стоит мост pywin32.")
        print("      Запусти PowerMill с открытым проектом и, если надо, пункт 27 меню.")
        return 1

    saved = pm_tool.saved_word()
    if saved:
        print(f"  Из прошлого раза известно слово: {saved} (попробуем его первым).")
    else:
        print("  Какое слово создаёт фрезу, пока не знаем — пункт переберёт "
              f"{', '.join(pm_tool.DEFAULT_WORDS)}.")
    print()

    steps = [
        ("Имя фрезы", "как она будет называться в проекте", "D16_Freza"),
        ("Диаметр, мм", "Enter — 16", "16"),
    ]
    wizard = Wizard(steps)
    while not wizard.finished:
        print(wizard.prompt(), end="")
        text = read_line("")
        if text is None:
            return 0
        action = wizard.submit(text)
        if action == "menu":
            print("Ничего не менял.")
            return 0
        if action == "help":
            print("  Enter — значение по умолчанию, «назад» — предыдущий вопрос.")
        print()

    name = (wizard.answers[0] or "D16_Freza").strip() or "D16_Freza"
    diameter_text = (wizard.answers[1] or "16").strip().replace(",", ".")
    try:
        diameter = float(diameter_text)
    except ValueError:
        print(f"  (!) «{diameter_text}» — не число, беру 16 мм.")
        diameter = 16.0

    print("=" * 64)
    print("  ЧТО БУДЕТ СДЕЛАНО (до выполнения)")
    print("=" * 64)
    print(f"  1) проверю, нет ли уже фрезы «{name}»")
    for word in pm_tool.word_order():
        print(f"  2) попробую: CREATE TOOL ; {word}")
    print(f"  3) настрою её: EDIT TOOL ; DIAMETER {diameter:g}, "
          "EDIT TOOL ; NUMBER COMMANDFROMUI 1")
    print(f"  4) переименую: RENAME Tool ; '{name}'")
    print("  5) запишу отчёт и запомню сработавшее слово для пункта 31")
    print()
    print("  Это меняет проект — работай на копии (её делает пункт 31).")
    print("  Если PowerMill всё же покажет окно с ошибкой, нажми в нём ОК:")
    print("  мы гасим такие окна командами DIALOGS, но версия может отличаться.")
    print()

    answer = ask_yes_no("  Создать фрезу сейчас? (да/нет) [нет]: ")
    if not answer:
        print("Ничего не менял. Макрос пункта 31 можно запустить как обычно.")
        return 0

    print()
    print("  Отправляю команды в PowerMill по одной…")
    session, _message = pm_com.connect()
    if session is None:
        print("  (!) PowerMill пропал — подключение потеряно.")
        return 1

    report = pm_tool.create_flat_tool(session, name=name, diameter=diameter,
                                      log=lambda text: print(f"   {text}"))
    print()
    text = report.format()
    print(text)
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(text, encoding="utf-8")
    print()
    print(f"  Отчёт: {REPORT_FILE}")
    print("  Открыть можно пунктом 29 меню.")
    if report.ok:
        print()
        print("  Дальше: пункт 31 — он увидит готовую фрезу и создавать не будет.")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
