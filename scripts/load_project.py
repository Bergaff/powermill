"""
Загрузка снимка проекта PowerMill (пункт 24 меню).

Как это выглядит для технолога:

1. В PowerMill запускается макрос разведки `output\\PM_PROBE.mac`
   (вкладка «Макрос» -> Выполнить, либо перетащить файл в окно PowerMill).
2. PowerMill печатает в окно сообщений списки объектов проекта.
3. Этот скрипт открывает блокнот, технолог вставляет туда скопированный текст
   и закрывает блокнот.
4. Ассистент разбирает текст, сохраняет `output\\project_context.json` и
   показывает проверки проекта.

После этого ассистент знает настоящие имена объектов и использует их в
макросах и ответах (команда `/project` в чате показывает снимок).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import project_context                      # noqa: E402
from src.applog import start_log                     # noqa: E402

TEMPLATE = """PowerMill AI — снимок проекта
=====================================

Как получить данные (30 секунд):
  1) открой PowerMill с нужным проектом;
  2) вкладка «Макрос» -> Выполнить -> выбери файл
     {probe}
  3) PowerMill напечатает списки объектов в окне сообщений;
  4) выдели там текст от строки
     --- POWERMILL AI PROBE START ---
     до строки
     --- POWERMILL AI PROBE END ---
     и скопируй его СЮДА, ниже этой строки;
  5) сохрани файл и закрой блокнот — ассистент всё разберёт.

Если макрос написал ошибку — вставь и текст ошибки, разберёмся.


===========================================================
ВСТАВЬ ДАННЫЕ НИЖЕ ЭТОЙ ЛИНИИ (старые строки можно стереть)
===========================================================
"""


def prepare_template(probe: Path) -> None:
    """Создаёт файл-шаблон, если его нет (или он пустой)."""
    if project_context.DUMP_FILE.exists() and \
            project_context.DUMP_FILE.stat().st_size > 200:
        return
    project_context.DUMP_FILE.parent.mkdir(parents=True, exist_ok=True)
    project_context.DUMP_FILE.write_text(TEMPLATE.format(probe=probe),
                                         encoding="utf-8")


def open_editor(path: Path) -> None:
    """Открывает блокнот и ждёт, пока его закроют (только Windows)."""
    if os.name != "nt":
        print("(не Windows — блокнот не открываю, читаю файл как есть)")
        return
    try:
        subprocess.call(["notepad.exe", str(path)])
    except Exception as error:  # noqa: BLE001
        print(f"(!) Блокнот не открылся: {error}")
        print(f"    Открой файл вручную: {path}")


def main() -> int:
    log = start_log("load_project")
    from config import OUTPUT_DIR
    from src.pm_macro import PROJECT_FILE

    auto = "--auto" in sys.argv

    # 1) живое чтение из уже запущенного PowerMill (по разведке пункта 27)
    live_rc = load_from_live(log)
    if live_rc is not None:
        return live_rc

    if auto:
        return load_from_macro(log)

    probe = OUTPUT_DIR / "PM_PROBE.mac"

    print("=" * 58)
    print("  СНИМОК ПРОЕКТА PowerMill")
    print("=" * 58)
    print()

    if not probe.exists():
        print(f"(!) Нет файла макроса разведки: {probe}")
        print("    Запусти пункт 23 меню — он создаст макрос.")
        return 2

    prepare_template(probe)
    print("Макрос разведки:")
    print(f"  {probe}")
    print()
    print("Сейчас откроется блокнот с инструкцией:")
    print(f"  {project_context.DUMP_FILE}")
    print("Вставь туда вывод из PowerMill, сохрани и закрой блокнот.")
    print()

    open_editor(project_context.DUMP_FILE)

    text = project_context.DUMP_FILE.read_text(encoding="utf-8", errors="replace")
    context = project_context.parse_dump(text)
    if context.get("_total", 0) == 0:
        print()
        print("(!) В файле не нашлось объектов проекта.")
        print("    Проверь, что вставил текст между строками PROBE START и PROBE END.")
        print(f"    Файл можно отредактировать и запустить пункт 24 снова.")
        return 3

    saved = project_context.save(context)
    print()
    print(project_context.summary(context))
    checks = project_context.format_checks(context)
    if checks:
        print()
        print(checks)
    print()
    print(f"💾 Сохранено: {saved}")
    print(f"Лог: {log}")
    print()
    print("Теперь ассистент знает твои имена объектов:")
    print("  /macro — макросы с настоящими именами")
    print("  /project — показать снимок и проверки")
    print("  /pm — попробовать живое подключение к PowerMill (шаг 2.1)")
    return 0


def load_from_live(log) -> int | None:
    """Снимок прямо из запущенного PowerMill. None — если подключиться нельзя."""
    from src import pm_com

    print("Пробую прочитать проект из запущенного PowerMill (живое API)...")
    context, message = pm_com.refresh_context()
    print(f"  {message}")

    if context is None:
        return None                      # не запущен / нет моста — идём дальше
    if not context.get("_total"):
        print("  Проект пуст или не открыт — жду открытия.")
        return None

    saved = project_context.CONTEXT_FILE
    checks = project_context.format_checks(context)
    if checks:
        print()
        print(checks)
    print()
    print("Готово — прочитано напрямую, без макросов и блокнота.")
    print(f"💾 Сохранено: {saved}")
    print()
    print("Теперь ассистент знает твои имена: /project, /macro, /ask")
    return 0


def load_from_macro(log) -> int:
    """Путь без блокнота: файл написал макрос PM_AI_SNAPSHOT.mac в PowerMill."""
    from src.pm_macro import PROJECT_FILE

    if not PROJECT_FILE.exists():
        print(f"(!) Нет файла снимка {PROJECT_FILE}")
        print("    Запусти в PowerMill макрос PM_AI_SNAPSHOT.mac (пункт 28 меню).")
        return 2

    text = PROJECT_FILE.read_text(encoding="utf-8", errors="replace")
    context = project_context.parse_dump(text)
    if context.get("_total", 0) == 0:
        print("(!) В файле снимка не нашлось объектов проекта.")
        print("    Проверь, что макрос выполнился без ошибок (окно сообщений PowerMill).")
        return 3

    context["_source"] = "макрос PowerMill (PM_AI_SNAPSHOT.mac)"
    saved = project_context.save(context)
    print(project_context.summary(context))
    checks = project_context.format_checks(context)
    if checks:
        print()
        print(checks)
    print()
    print(f"💾 Сохранено: {saved}")
    print()
    print("Теперь ассистент знает твои имена: /project, /macro, /ask")
    if "--verbose" in sys.argv:
        print(f"Лог: {log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
