"""
СВЯЗКА С POWERMILL ОДНИМ ЗАПУСКОМ (пункт 47).

Зачем
-----
Связь с PowerMill — это три шага, которые до сих пор надо было помнить:
мост (пункт 27) → макросы внутри PowerMill (пункт 28) → проверка делом
(пункт 41). Если что-то из этого пропущено, следующий шаг падал непонятно
почему. Здесь они идут по порядку сами, а в конце — один отчёт, который можно
целиком прислать в чат: `output\\pm_link_setup_report.txt`.

Что делает каждый шаг
---------------------
1. **Мост** — есть ли pywin32 (связь с PowerMill как с COM-сервером). Если нет,
   предлагает поставить его тут же (как пункт 27), и только с согласия —
   установка идёт в интернет.
2. **Макросы** — пишет наши макросы и копирует их в папки PowerMill, чтобы он
   видел их в списке «Макрос → Выполнить».
3. **Связь делом** — подключается к ЗАПУЩЕННОМУ PowerMill, читает проект и
   просит PowerMill выполнить `PM_AI_TEST.mac`; макрос пишет файл-отметку,
   и по обновлению файла видно, что PowerMill действительно выполнил команду.

Проект не меняется: макрос только пишет свои файлы-отметки.

Запуск: scripts\\link_setup.bat (пункт 47 меню) — двойным кликом.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import link_check, pm_com, pm_macro              # noqa: E402
from src.applog import start_log                          # noqa: E402


def _ask_yes(question: str, default_yes: bool = True) -> bool:
    """Свой маленький вопрос «д/н» — чтобы не тянуть сюда лишние модули."""
    hint = "Д/н" if default_yes else "д/Н"
    while True:
        try:
            answer = input(f"{question} [{hint}]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return default_yes
        if not answer:
            return default_yes
        if answer in ("д", "да", "y", "yes"):
            return True
        if answer in ("н", "нет", "n", "no"):
            return False
        print("  Ответь «д» или «н».")


def _blank(print_) -> None:
    """Пустая строка: у «печати» в тестах может не быть аргументов по умолчанию."""
    print_("")


def check_bridge(print_, ask_yes=None) -> tuple[bool, list[str]]:
    """Шаг 1: мост. Есть — хорошо; нет — предлагаем поставить (это пункт 27)."""
    notes: list[str] = []
    ask_yes = ask_yes or _ask_yes
    bridges = pm_com.bridges()
    if bridges.get("pywin32"):
        print_("  ✔ мост pywin32 на месте")
        return True, notes

    print_("  ✘ pywin32 не установлен — без него PowerMill команд не услышит.")
    print_("    Это тот же шаг, что пункт 27 меню (мост к PowerMill).")
    if not ask_yes("  Поставить pywin32 сейчас? (нужен интернет)", True):
        notes.append("мост не ставили — поставить его можно пунктом 27 меню")
        print_("    Ладно: макросы сделаю, а связь проверить не выйдет.")
        return False, notes

    from scripts.install_bridge import check_package, pip_install

    print_("    Ставлю pywin32... (может занять минуту)")
    ok, message = pip_install("pywin32")
    if not ok:
        notes.append(f"pywin32 не поставился: {message}")
        print_(f"  ✘ установка не прошла: {message}")
        print_("    Проверь интернет и повтори; либо пункт 27 меню.")
        return False, notes
    import_ok, import_message = check_package(("win32com.client", "pythoncom"))
    if import_ok:
        notes.append("pywin32 поставлен этой связкой")
        print_(f"  ✔ pywin32 установлен ({import_message})")
        return True, notes
    notes.append(f"pywin32 поставился, но не импортируется: {import_message}")
    print_(f"  ✘ поставился, но не импортируется: {import_message}")
    print_("    Обычно помогает перезапуск этого батника.")
    return False, notes


def prepare_macros(print_) -> tuple[int, list[str]]:
    """Шаг 2: наши макросы — в папки PowerMill (то же, что пункт 28)."""
    notes: list[str] = []
    try:
        written = pm_macro.write_all()
    except OSError as error:
        notes.append(f"макросы не записались: {error}")
        print_(f"  ✘ макросы не записались: {error}")
        return 0, notes
    print_(f"  ✔ записано макросов: {len(written)} — папка {pm_macro.MACRO_DIR}")

    copied, failed = pm_macro.copy_into_power_mill()
    for folder, error in failed:
        print_(f"  (!) {folder}: {error}")
    if copied:
        print_(f"  ✔ внутри PowerMill: {len(copied)} файлов в "
               f"{len({path.parent for path in copied})} папках")
    else:
        print_("  — папки макросов PowerMill не нашлись: макросы лежат в")
        print_(f"    {pm_macro.MACRO_DIR}")
        print_("    В PowerMill: Файл → Параметры → Пути макросов — добавь эту папку.")
        notes.append("макросы не скопированы в PowerMill — добавь папку в Macro Paths")
    if failed:
        notes.append("часть копий не удалась (права администратора) — можно запускать "
                     "макрос прямо из нашей папки")
    return len(copied), notes


def run(print_=None, ask_yes=None) -> tuple[bool, list[str], link_check.LinkReport]:
    """Вся связка. Возвращает (удалось ли проверить связь делом, заметки, отчёт)."""
    print_ = print_ or print
    ask_yes = ask_yes or _ask_yes
    notes: list[str] = []

    print_("=" * 64)
    print_("  СВЯЗКА С POWERMILL — мост, макросы, проверка делом (пункт 47)")
    print_("=" * 64)
    _blank(print_)
    print_("Проект не меняется: макрос-самопроверка только пишет свои файлы-отметки.")
    _blank(print_)

    print_("[1/3] Мост Python ↔ PowerMill")
    bridge_ok, bridge_notes = check_bridge(print_, ask_yes)
    notes.extend(bridge_notes)
    _blank(print_)

    print_("[2/3] Макросы ассистента внутри PowerMill")
    prepare_macros(print_)
    _blank(print_)

    print_("[3/3] Проверка связи делом")
    report = link_check.run()
    for line in report.format().splitlines():
        print_("  " + line)
    # советы уже внутри отчёта — в «Заметки» их не дублируем
    _blank(print_)
    print_("ИТОГ: " + report.summary())

    if not bridge_ok and report.roundtrip is not True:
        print_("Мост поставить не удалось — начни с пункта 27 меню, потом повтори 47.")
    elif report.roundtrip is True:
        print_("Дальше: пункт 39 (окно приложения) покажет эту же связь на кнопке,")
        print_("а пункты 30–37 начнут писать в проект.")
    else:
        print_("Если PowerMill запущен и проект открыт — пришли отчёт в чат,")
        print_("посмотрим, на каком шаге PowerMill не ответил.")

    return report.roundtrip is True, notes, report


def format_report(ok: bool, notes: list[str], report: link_check.LinkReport) -> str:
    import time

    lines = [
        "PowerMill AI — связка с PowerMill (пункт 47)",
        time.strftime("Проверено: %d.%m.%Y %H:%M"),
        "",
        "Шаги: мост (27) → макросы (28) → проверка делом (41).",
        "",
        report.format(),
        "",
        "ИТОГ: " + ("связь работает в обе стороны — PowerMill выполнил наш макрос"
                     if ok else report.summary()),
        "",
    ]
    if notes:
        lines.append("Заметки:")
        lines.extend(f"  • {item}" for item in notes)
        lines.append("")
    lines.append("Этот файл можно целиком прислать в чат.")
    return "\n".join(lines)


def main() -> int:
    log = start_log("link_setup")
    print(f"Лог: {log}")
    print_ = print
    ok, notes, report = run(print_)

    from config import OUTPUT_DIR

    path = Path(OUTPUT_DIR) / "pm_link_setup_report.txt"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(format_report(ok, notes, report), encoding="utf-8")
        _blank(print_)
        print_(f"📝 Отчёт: {path}")
        print_("   (он же в пункте 29 меню — «Показать отчёты»)")
    except OSError as error:
        print_(f"(!) отчёт не записался: {error}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
