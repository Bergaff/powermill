"""
СОСТОЯНИЕ БАЗЫ ЗНАНИЙ: что уже собрано, а что нет.

Читает только файлы на диске — Ollama, chromadb и эмбеддинги не нужны,
поэтому запускается мгновенно. Запуск: scripts\\base_status.bat
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (  # noqa: E402
    CHROMA_DIR,
    CURRENT_MODE,
    EMBEDDING_MODEL,
    HELP_SEARCH_DB,
    HELP_DIR,
    LLM_CODE_MODEL,
    LLM_MODEL,
    OUTPUT_DIR,
)


def folder_size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            continue
    return total / 1e6


def count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    n = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def read_state() -> dict:
    """Состояние последнего разбора (пишет src/html_parser)."""
    path = OUTPUT_DIR / "help_parse_state.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def line(title: str) -> None:
    print("\n" + "-" * 58)
    print(f"  {title}")
    print("-" * 58)


def ok(text: str) -> None:
    print(f"  [ГОТОВО] {text}")


def todo(text: str, hint: str = "") -> None:
    print(f"  [НЕТ]    {text}")
    if hint:
        print(f"           -> {hint}")


def main() -> None:
    print("=" * 58)
    print("  СОСТОЯНИЕ БАЗЫ ЗНАНИЙ PowerMill AI")
    print(f"  Режим: {CURRENT_MODE.upper()} | модели: {LLM_MODEL}, {LLM_CODE_MODEL}")
    print(f"  Эмбеддинги: {EMBEDDING_MODEL}")
    print("=" * 58)

    line("1. Справка PowerMill")
    print(f"  Путь справки: {HELP_DIR}  (есть: {HELP_DIR.exists()})")
    pages_file = OUTPUT_DIR / "help_pages.jsonl"
    pages = count_jsonl(pages_file)
    state = read_state()
    probe = bool(state) and not state.get("complete", True)
    if pages and probe:
        size = pages_file.stat().st_size / 1e6
        print(f"  [ПРОБА]  Разобрано {pages} из {state.get('files_total', '?')} страниц "
              f"({size:.1f} МБ)")
        print("           -> это пробный запуск; полная база: start_parse_help.bat (пункт 4)")
    elif pages:
        size = pages_file.stat().st_size / 1e6
        when = f", {state.get('finished_at')}" if state else ""
        ok(f"Разобрано страниц: {pages} ({size:.1f} МБ){when}")
        if state:
            ok(f"Терминов привязано к статьям: {state.get('terms_linked', 0)}")
    else:
        todo("Справка ещё не разобрана",
             "запусти start_parse_help.bat  (пробно: start_parse_help.bat 30)")

    report = OUTPUT_DIR / "help_report.txt"
    toc = OUTPUT_DIR / "help_toc.txt"
    if report.exists():
        ok(f"Отчёт по разбору: {report}")
    if toc.exists():
        ok(f"Дерево тем: {toc}")

    line("2. Индекс быстрого поиска (FTS5, без ИИ)")
    if HELP_SEARCH_DB.exists():
        try:
            conn = sqlite3.connect(str(HELP_SEARCH_DB))
            n = conn.execute("SELECT count(*) FROM pages").fetchone()[0]
            conn.close()
            size = HELP_SEARCH_DB.stat().st_size / 1e6
            ok(f"Страниц в индексе: {n} ({size:.1f} МБ) — {HELP_SEARCH_DB.name}")
        except sqlite3.Error as e:
            todo(f"Индекс повреждён: {e}", "запусти start_parse_help.bat")
    else:
        todo("Индекса нет", "запусти start_parse_help.bat")

    line("3. Векторная база (ChromaDB)")
    size_mb = folder_size_mb(CHROMA_DIR)
    if size_mb > 0.1:
        ok(f"Папка {CHROMA_DIR} — {size_mb:.1f} МБ")
    else:
        todo("Векторная база пуста",
             "запусти start_reindex_help.bat (или ночью start_night_indexing.bat)")

    line("4. Прочие источники")
    pdfs = sorted((OUTPUT_DIR.parent / "data" / "pdf").glob("*.pdf"))
    macros = sorted((OUTPUT_DIR.parent / "data" / "macros").glob("*.mac"))
    videos = [p for p in (OUTPUT_DIR.parent / "data" / "videos").iterdir()
              if p.is_file()] if (OUTPUT_DIR.parent / "data" / "videos").exists() else []
    transcripts = sorted(OUTPUT_DIR.glob("*_transcript.txt"))
    generated = sorted((OUTPUT_DIR / "macros").glob("*.mac")) if (OUTPUT_DIR / "macros").exists() else []
    print(f"  PDF в data\\pdf:            {len(pdfs)}")
    print(f"  Видео в data\\videos:       {len(videos)}")
    print(f"  Транскриптов видео:        {len(transcripts)}")
    print(f"  Макросов в data\\macros:    {len(macros)}")
    print(f"  Сгенерировано ассистентом: {len(generated)} (output\\macros)")

    line("ИТОГ")
    steps: list[str] = []
    if not pages:
        steps.append("start_parse_help.bat              — разобрать справку")
    elif probe:
        steps.append("start_parse_help.bat              — полный разбор (сейчас только проба)")
    if not HELP_SEARCH_DB.exists():
        steps.append("start_parse_help.bat              — собрать индекс поиска")
    if size_mb <= 0.1:
        steps.append("start_reindex_help.bat            — собрать векторную базу")
    if not steps:
        print("  Всё готово. Запускай start_work_chat.bat и задавай вопросы.")
        print("  Быстрый поиск без ИИ: start_help_search.bat")
        print("  Калькулятор режимов:   start_cutting.bat")
    else:
        print("  Осталось выполнить:")
        for i, s in enumerate(steps, 1):
            print(f"    {i}. {s}")
    print()


if __name__ == "__main__":
    main()
