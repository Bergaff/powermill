"""
Подготовка плагина PowerMill (пункт 25 меню).

Ничего не устанавливает и не меняет в PowerMill. Ищет в установке папку
`file\\plugins` (Documentation, Framework, Installers, Solutions), копирует
каркас и примеры к нам, вытаскивает факты о каркасе и проверяет инструменты
сборки (csc.exe, regasm.exe, tlbimp.exe, dotnet).

Результат: отчёт `output\\plugin_report.txt`, который нужно прислать в чат —
по нему пишется код плагина под конкретную версию PowerMill.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import plugin_scaffold                     # noqa: E402
from src.applog import start_log                    # noqa: E402


def main() -> int:
    log = start_log("prepare_plugin")
    print(f"Лог этого запуска: {log}")
    print()

    text, found = plugin_scaffold.report()
    print(text)

    from config import OUTPUT_DIR

    report_file = OUTPUT_DIR / "plugin_report.txt"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(text, encoding="utf-8")
    print()
    print(f"📝 Отчёт: {report_file}")

    plugin_root = plugin_scaffold.PLUGIN_ROOT
    print(f"📁 Рабочая папка плагина: {plugin_root}")

    if found:
        print()
        print("Пришли отчёт в чат — я подгоню код плагина под твою установку.")
        print("Пока плагина нет, всё остальное работает: пункты 1–4, 23, 24.")
    else:
        print()
        print("Папки плагинов в поставке нет. Варианты:")
        print("  1) остаться на маршруте «макросы + снимок проекта» (пункты 23–24) —")
        print("     это уже даёт ассистенту знание твоего проекта;")
        print("  2) собрать плагин по документации Autodesk "
              "(нужна Visual Studio Community).")
    print()
    print("Макрос-разведчик и снимок проекта работают без плагина и без API —")
    print("это надёжная основа, на которой плагин потом только показывает окно.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
