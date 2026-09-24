"""
Загрузка снимка проекта PowerMill (пункт 24 меню).

Порядок попыток — от самого удобного к самому ручному:

1. **Живьём** (если PowerMill запущен) — ассистент присоединяется к программе
   через COM и читает проект сам: `src/pm_com.py`. Ни макросов, ни блокнота.
2. **Файл от макроса** — если в PowerMill выполнен `PM_AI_SNAPSHOT.mac`
   (пункт 28), он пишет `output\\pm_project.txt`; разбираем его.
3. **Вручную** — макрос `PM_PROBE.mac` + блокнот: печатает списки в окне
   сообщений PowerMill, ты копируешь текст в блокнот. Работает всегда.

После любого из путей получается один и тот же `output\\project_context.json`,
поэтому `/project`, `/macro` и `/ask` сразу видят настоящие имена объектов.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import project_context                      # noqa: E402
from src.applog import start_log                     # noqa: E402

TEMPLATE = """PowerMill AI — снимок проекта
=====================================

Есть три способа, от быстрого к ручному. Если ты это читаешь — значит первые
два не сработали.

СПОСОБ 1 (ничего не копировать): открой PowerMill с проектом и запусти
  пункт 24 меню снова — ассистент прочитает проект сам (живое API).

СПОСОБ 2 (без блокнота): в PowerMill выполни макрос
  {snapshot}
он сам запишет файл, и пункт 24 разберёт его.

СПОСОБ 3 (этот файл): макрос {probe}
  сам записывает снимок в файл, копировать ничего не нужно.
  Если он напечатал текст в окне сообщений PowerMill — можно скопировать
  кусок от строки --- POWERMILL AI PROBE START --- до --- POWERMILL AI PROBE END ---
  и вставить его СЮДА, ниже линии, затем сохранить и закрыть блокнот.

Если макрос написал ошибку — вставь и текст ошибки, разберёмся.


===========================================================
ВСТАВЬ ДАННЫЕ НИЖЕ ЭТОЙ ЛИНИИ (старые строки можно стереть)
===========================================================
"""


def prepare_template(probe: Path, snapshot: Path | None = None) -> None:
    """Создаёт файл-шаблон, если его нет (или он почти пустой)."""
    if project_context.DUMP_FILE.exists() and \
            project_context.DUMP_FILE.stat().st_size > 200:
        return
    project_context.DUMP_FILE.parent.mkdir(parents=True, exist_ok=True)
    project_context.DUMP_FILE.write_text(
        TEMPLATE.format(probe=probe, snapshot=snapshot or probe),
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


def _save_and_report(context: dict, source: str) -> int:
    """Общий финал: сохранить снимок, показать итог и проверки."""
    context["_source"] = source
    saved = project_context.save(context)
    print()
    print(project_context.summary(context))
    checks = project_context.format_checks(context)
    if checks:
        print()
        print(checks)
    print()
    print(f"💾 Сохранено: {saved}")
    print()
    print("Теперь ассистент знает твои имена: /project, /macro, /ask")
    return 0


def load_from_live(log) -> int | None:
    """Снимок прямо из запущенного PowerMill. None — если подключиться нельзя."""
    from src import pm_com

    print("Пробую прочитать проект напрямую из PowerMill (живое API)...")
    context, message = pm_com.refresh_context()
    for line in str(message).splitlines():
        print(f"  {line}")

    if context is None:
        return None                      # не запущен / нет моста — идём дальше
    if not context.get("_total"):
        print("  В проекте не видно объектов — возможно, проект не открыт.")
        return None

    return _save_and_report(context, context.get("_source", "живой PowerMill (COM)"))


def read_macro_file() -> tuple[dict | None, str]:
    """Файл, который пишет макрос PM_AI_SNAPSHOT.mac (пункт 28)."""
    from src.pm_macro import PROJECT_FILE

    path = Path(PROJECT_FILE)
    if not path.exists() or path.stat().st_size < 10:
        return None, f"файла нет ({path})"

    age_minutes = (time.time() - path.stat().st_mtime) / 60
    text = path.read_text(encoding="utf-8", errors="replace")
    context = project_context.parse_dump(text)
    if not context.get("_total", 0):
        return None, f"в файле нет объектов ({path})"
    if age_minutes > 60:
        return context, (f"файл от {time.strftime('%d.%m %H:%M', time.localtime(path.stat().st_mtime))} "
                         f"— если проект другой, запусти PM_AI_SNAPSHOT.mac заново")
    return context, f"свежий файл от макроса ({path.name})"


def load_from_macro(log) -> int:
    """Разбор файла, записанного макросом PM_AI_SNAPSHOT.mac (без блокнота)."""
    context, message = read_macro_file()
    if context is None:
        print("=" * 58)
        print("  СНИМОК ПРОЕКТА PowerMill")
        print("=" * 58)
        print()
        print(f"(!) Не вышло взять снимок автоматически: {message}")
        print()
        print("Что сделать (любой из вариантов):")
        print("  1) открой PowerMill с проектом и запусти пункт 24 снова —")
        print("     ассистент прочитает проект сам (живое API);")
        print("  2) в PowerMill выполни макрос PM_AI_SNAPSHOT.mac (пункт 28),")
        print("     он запишет файл сам — потом снова пункт 24.")
        return 3

    print(f"Снимок взят из файла макроса: {message}")
    return _save_and_report(context, "макрос PM_AI_SNAPSHOT.mac (пункт 28)")


def main() -> int:
    log = start_log("load_project")
    from config import OUTPUT_DIR
    from src import power_mill_link
    from src.pm_macro import MACRO_DIR

    auto = "--auto" in sys.argv

    # 1) живое чтение из уже запущенного PowerMill (по разведке пункта 27)
    live_rc = load_from_live(log)
    if live_rc is not None:
        return live_rc

    # 2) файл, который пишет макрос PM_AI_SNAPSHOT.mac (без блокнота)
    context, macro_message = read_macro_file()
    if context is not None:
        print(f"Живое чтение не вышло, но есть {macro_message}")
        return _save_and_report(context, "макрос PM_AI_SNAPSHOT.mac (пункт 28)")

    if auto:
        return load_from_macro(log)

    # 3) ручной путь: макрос разведки + блокнот (работает всегда)
    probe = OUTPUT_DIR / "PM_PROBE.mac"
    print()
    print("=" * 58)
    print("  СНИМОК ПРОЕКТА PowerMill (ручной способ)")
    print("=" * 58)
    print()
    print("Живьём прочитать не удалось — нужен запущенный PowerMill")
    print("(пункт 27 показал, что мост Python стоит; проверь, что PowerMill открыт).")
    print()

    if not probe.exists():
        print(f"Создаю макрос разведки: {probe}")
        power_mill_link.write_probe_macro(OUTPUT_DIR)

    snapshot = MACRO_DIR / "PM_AI_SNAPSHOT.mac"
    prepare_template(probe, snapshot)

    print("Сейчас откроется блокнот с инструкцией:")
    print(f"  {project_context.DUMP_FILE}")
    print("Варианты: живое чтение (PowerMill открыт), макрос PM_AI_SNAPSHOT.mac")
    print("или скопировать вывод PM_PROBE.mac в блокнот.")
    print()

    open_editor(project_context.DUMP_FILE)

    text = project_context.DUMP_FILE.read_text(encoding="utf-8", errors="replace")
    context = project_context.parse_dump(text)
    if context.get("_total", 0) == 0:
        print()
        print("(!) В файле не нашлось объектов проекта.")
        print("    Проверь, что вставил текст между строками PROBE START и PROBE END.")
        print("    Файл можно отредактировать и запустить пункт 24 снова.")
        return 3

    return _save_and_report(context, f"ручной снимок ({project_context.DUMP_FILE.name})")


if __name__ == "__main__":
    sys.exit(main())
