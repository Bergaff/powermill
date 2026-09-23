"""
ПРЕДПОЛЁТНАЯ ПРОВЕРКА для батников.

Батники не должны падать с невнятными ошибками: перед запуском чата/индексации
этот модуль проверяет, всё ли готово, и по-русски объясняет, что сделать.

Использование (из .bat):
    python -m scripts.preflight chat      Проверка перед чатом
    python -m scripts.preflight parse     Перед разбором справки
    python -m scripts.preflight reindex   Перед сборкой векторной базы
    python -m scripts.preflight search    Перед поиском по справке

Код возврата 0 — можно работать, 1 — чего-то не хватает (сообщение уже выведено).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from config import (  # noqa: E402
    CHROMA_DIR,
    DATA_ROOT,
    HELP_DIR,
    HELP_SEARCH_DB,
    OUTPUT_DIR,
)

GREEN, YELLOW, RED, RESET = "", "", "", ""


def ok(text: str) -> None:
    print(f"  [OK]     {text}")


def warn(text: str) -> None:
    print(f"  [ВНИМАНИЕ] {text}")


def bad(text: str) -> None:
    print(f"  [НЕТ]    {text}")


def has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def help_parsed() -> int:
    """Сколько страниц разобрано (0 — не разобрано)."""
    pages_file = OUTPUT_DIR / "help_pages.jsonl"
    if not pages_file.exists():
        return 0
    try:
        with open(pages_file, encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0


def check_parse() -> int:
    print("Проверка перед разбором справки:")
    problems = 0

    if not HELP_DIR.exists():
        bad(f"папка справки не найдена: {HELP_DIR}")
        print("           -> scripts\\set_help_path.bat (указать путь вручную)")
        print("           -> scripts\\find_help.bat      (поиск справки на диске)")
        problems += 1
    else:
        ok(f"справка найдена: {HELP_DIR}")

    if not has_module("bs4"):
        bad("нет библиотеки beautifulsoup4")
        print("           -> запусти setup.bat (он установит все зависимости)")
        problems += 1
    else:
        ok("beautifulsoup4 на месте")

    if not DATA_ROOT.exists():
        warn(f"диска/папки {DATA_ROOT} нет — данные будут писаться по этому пути")
    else:
        ok(f"папка данных: {DATA_ROOT}")

    return 1 if problems else 0


def check_search() -> int:
    print("Проверка перед поиском по справке:")
    if help_parsed() == 0:
        bad("справка ещё не разобрана (нет output\\help_pages.jsonl)")
        print("           -> запусти start_parse_help.bat   (пробно: start_parse_help.bat 30)")
        return 1
    ok(f"разобрано страниц: {help_parsed()}")
    if not HELP_SEARCH_DB.exists():
        warn("индекса поиска ещё нет — он соберётся автоматически сейчас")
    else:
        ok("индекс поиска на месте")
    return 0


def check_reindex() -> int:
    print("Проверка перед сборкой векторной базы:")
    problems = 0

    missing = [m for m in ("torch", "sentence_transformers", "chromadb") if not has_module(m)]
    if missing:
        bad("не установлены библиотеки: " + ", ".join(missing))
        print("           -> запусти setup.bat")
        print("           -> если не скачался pytorch: scripts\\install_torch.bat")
        problems += 1
    else:
        ok("torch, sentence-transformers, chromadb на месте")

    pages = help_parsed()
    if pages == 0:
        bad("справка ещё не разобрана — индексировать нечего")
        print("           -> сначала: start_parse_help.bat")
        problems += 1
    else:
        ok(f"разобрано страниц: {pages}")

    if not DATA_ROOT.exists():
        warn(f"папка {DATA_ROOT} отсутствует — создам по ходу дела")
    return 1 if problems else 0


def check_chat() -> int:
    print("Проверка перед запуском чата:")
    problems = 0

    missing = [m for m in ("ollama",) if not has_module(m)]
    if missing:
        bad("нет библиотеки ollama (pip install ollama) — запусти setup.bat")
        problems += 1
    else:
        ok("клиент Ollama на месте")

    if not has_module("chromadb") or not has_module("sentence_transformers"):
        bad("нет chromadb / sentence-transformers — запусти setup.bat")
        problems += 1
    else:
        ok("chromadb и sentence-transformers на месте")

    pages = help_parsed()
    if pages == 0:
        warn("справка не разобрана — ассистент ответит только по PDF/видео, если они есть")
        print("           -> start_parse_help.bat")
    else:
        ok(f"разобрано страниц справки: {pages}")

    if not HELP_SEARCH_DB.exists():
        warn("индекс быстрого поиска не собран — соберётся при старте (займёт ~10 сек)")
    else:
        ok("индекс быстрого поиска на месте")

    if CHROMA_DIR.exists() and any(CHROMA_DIR.iterdir()):
        ok(f"векторная база найдена: {CHROMA_DIR}")
    else:
        warn("векторная база пуста — ассистент будет работать только на ключевых словах")
        print("           -> start_reindex_help.bat (собрать, лучше ночью)")

    print()
    print("  Подсказка: чат работает и без ИИ-модели —")
    print("             команда /sources ищет по справке мгновенно.")
    return 1 if problems else 0


CHECKS = {
    "parse": check_parse,
    "search": check_search,
    "reindex": check_reindex,
    "chat": check_chat,
}


def main() -> int:
    what = (sys.argv[1] if len(sys.argv) > 1 else "chat").lower()
    check = CHECKS.get(what)
    if check is None:
        print(f"Неизвестная проверка: {what}. Доступно: {', '.join(CHECKS)}")
        return 1
    code = check()
    print()
    if code:
        print("  [СТОП] Сначала исправь отмеченное выше.")
    else:
        print("  [ГОТОВО] Можно запускать.")
    return code


if __name__ == "__main__":
    sys.exit(main())
