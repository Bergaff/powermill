"""
Быстрый keyword-поиск по оффлайн-справке: SQLite FTS5 (стандартная библиотека).

Зачем, если есть ChromaDB:
  * вектора «размазывают» точные термины: `Thickness`, `HOLDER_CLEARANCE`,
    `GUID`, названия кнопок — а технолог спрашивает именно ими;
  * FTS мгновенный и не требует GPU/эмбеддингов — работает, пока Ollama молчит;
  * вместе с векторами даёт гибридный поиск (см. src/retrieval.py).

Индекс строится из output/help_pages.jsonl (его пишет src.html_parser).
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from config import HELP_SEARCH_DB, OUTPUT_DIR

PAGES_FILE = OUTPUT_DIR / "help_pages.jsonl"

# Версия схемы FTS-таблицы. При несовпадении индекс пересоздаётся автоматически
# (данные берутся из help_pages.jsonl, потерять их нельзя).
SCHEMA_VERSION = 3

_TOKEN_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё_]{2,}")
_STOPWORDS = {
    "как", "что", "где", "для", "или", "это", "чем", "мне", "the", "and", "for",
    "how", "what", "with", "в", "на", "по", "из", "и", "в", "не", "а", "но",
    "сделать", "нужно", "можно", "подскажи", "объясни", "разница", "отличие",
}

# Грубое «стемминг»-усечение русских окончаний: «обработки» -> «обработ».
# Нужно, потому что FTS5 не умеет морфологию, а в справке формы слов разные.
_RU_ENDINGS = (
    "иями", "ями", "ами", "ией", "иях", "иям", "ого", "его", "ому", "ему",
    "ыми", "ими", "ая", "яя", "ое", "ее", "ые", "ие", "ый", "ий", "ой", "ей",
    "ax", "ях", "ах", "ов", "ев", "ий", "ия", "ию", "ие", "ии", "am", "ям",
    "ой", "ых", "их", "ую", "юю", "ся", "сь", "ть", "ешь", "ишь", "ете",
    "ать", "ять", "ить", "еть", "ли", "ла", "ло", "ну", "нешь",
    "ы", "и", "а", "я", "у", "ю", "е", "о", "ь", "й", "s", "es", "ed", "ing",
)


def stem(word: str) -> str:
    """Усекает слово до «корня» для префиксного поиска (не менее 4 символов)."""
    w = word.lower()
    for end in sorted(_RU_ENDINGS, key=len, reverse=True):
        if len(w) - len(end) >= 4 and w.endswith(end):
            return w[: -len(end)]
    return w


def tokenize(query: str) -> list[str]:
    """Запрос -> значимые токены (без стоп-слов).

    Если значимых слов нет («как и в на») — возвращаем пустой список:
    такой запрос всё равно не несёт смысла, а мусорные попадания хуже пропуска.
    """
    tokens = [t.lower() for t in _TOKEN_RE.findall(query)]
    return [t for t in tokens if t not in _STOPWORDS]


class HelpSearch:
    """FTS5-индекс по страницам справки."""

    def __init__(self, db_path: Path | None = None, pages_file: Path | None = None):
        self.db_path = Path(db_path or HELP_SEARCH_DB)
        self.pages_file = Path(pages_file or PAGES_FILE)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    # ---------------- подключение ----------------
    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            conn = sqlite3.connect(str(self.db_path))
            _create = (
                "CREATE VIRTUAL TABLE IF NOT EXISTS pages USING fts5("
                "source, title, section, alias, contextid, kind UNINDEXED, body, "
                "tokenize=\"unicode61 remove_diacritics 2\")"
            )
            conn.execute(_create)
            version = conn.execute("PRAGMA user_version").fetchone()[0] or 0
            if version < SCHEMA_VERSION:
                # смена схемы индекса: пересоздаём (данные всё равно из jsonl)
                conn.execute("DROP TABLE IF EXISTS pages")
                conn.execute(_create)
                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                conn.commit()
            self._conn = conn
        return self._conn

    def is_stale(self) -> bool:
        """Индекс отсутствует или старше help_pages.jsonl."""
        if not self.db_path.exists() or not self.pages_file.exists():
            return True
        try:
            return self.db_path.stat().st_mtime < self.pages_file.stat().st_mtime
        except OSError:
            return True

    def count(self) -> int:
        try:
            row = self.conn.execute("SELECT count(*) FROM pages").fetchone()
            return int(row[0]) if row else 0
        except sqlite3.Error:
            return 0

    # ---------------- индексация ----------------
    def build(self, pages: list[dict] | None = None, verbose: bool = True) -> int:
        """(Пере)строить индекс из help_pages.jsonl."""
        if pages is None:
            if not self.pages_file.exists():
                if verbose:
                    print(f"(!) Нет файла {self.pages_file}")
                    print("    Сначала разбери справку: start_parse_help.bat")
                    print("    (пункт 4 или 5 в start_menu.bat)")
                return 0
            pages = [
                json.loads(line)
                for line in self.pages_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        conn = self.conn
        conn.execute("DELETE FROM pages")
        rows = [
            (
                p.get("source", ""),
                p.get("title", ""),
                p.get("breadcrumb", "") or p.get("section", ""),
                " ; ".join(p.get("aliases") or []),
                " ".join(p.get("contextids") or ([p["contextid"]] if p.get("contextid") else [])),
                p.get("kind", "page"),
                p.get("text", ""),
            )
            for p in pages
            if (p.get("text") or "").strip()
        ]
        conn.executemany(
            "INSERT INTO pages (source, title, section, alias, contextid, kind, body) "
            "VALUES (?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
        if verbose:
            print(f"🔎 FTS-индекс: {len(rows)} страниц -> {self.db_path}")
        return len(rows)

    def ensure_index(self, verbose: bool = True) -> int:
        """Строит индекс, если он отсутствует или устарел."""
        if self.is_stale():
            return self.build(verbose=verbose)
        return self.count()

    # ---------------- поиск ----------------
    def _query_string(self, tokens: list[str], mode: str) -> str:
        parts = []
        for tok in tokens:
            body = re.sub(r"[^0-9A-Za-zА-Яа-яЁё_]", "", tok)
            if not body:
                continue
            root = stem(body) if len(body) > 4 else body
            parts.append(f'"{root}"*' if mode == "prefix" else f'"{body}"')
        joiner = " AND " if mode == "and" else " OR "
        return joiner.join(parts)

    def search(self, query: str, top_k: int = 6) -> list[dict]:
        """Поиск: сначала строгий AND с префиксами, потом OR, потом подстрокой."""
        tokens = tokenize(query)
        if not tokens:
            return []
        sql = (
            "SELECT source, title, section, kind, "
            "snippet(pages, 6, '«', '»', ' … ', 18) AS snip, bm25(pages) AS rank "
            "FROM pages WHERE pages MATCH ? ORDER BY rank LIMIT ?"
        )
        # mode -> strict: строгий AND считаем надёжным попаданием,
        # OR/LIKE — «возможно релевантно» (используется в src.retrieval)
        attempts = [
            ("and", self._query_string(tokens, "prefix"), True),
            ("or", self._query_string(tokens, "or"), False),
        ]
        for _mode, match, strict in attempts:
            if not match:
                continue
            try:
                rows = self.conn.execute(sql, (match, top_k)).fetchall()
            except sqlite3.Error:
                rows = []
            if rows:
                return [
                    {
                        "source": r[0],
                        "title": r[1],
                        "breadcrumb": r[2],
                        "kind": r[3],
                        "text": r[4],
                        "score": -float(r[5]),   # bm25: меньше = лучше -> больше = лучше
                        "found_by": "fts",
                        "strict": strict,
                    }
                    for r in rows
                ]

        # последний шанс: подстрока (опечатки, латиница внутри кириллицы и т.п.)
        needle = tokens[0]
        rows = self.conn.execute(
            "SELECT source, title, section, kind, substr(body, 1, 400) "
            "FROM pages WHERE lower(body) LIKE ? LIMIT ?",
            (f"%{needle.lower()}%", top_k),
        ).fetchall()
        return [
            {
                "source": r[0],
                "title": r[1],
                "breadcrumb": r[2],
                "kind": r[3],
                "text": r[4],
                "score": 0.0,
                "found_by": "like",
                "strict": False,
            }
            for r in rows
        ]

    def page_text(self, source: str) -> str:
        row = self.conn.execute(
            "SELECT body FROM pages WHERE source = ? LIMIT 1", (source,)
        ).fetchone()
        return row[0] if row else ""

    def sections(self, limit: int = 0) -> list[tuple[str, int]]:
        """Разделы справки и число страниц в них (для отчёта/навигации)."""
        rows = self.conn.execute(
            "SELECT section, count(*) c FROM pages GROUP BY section ORDER BY c DESC"
        ).fetchall()
        return rows[:limit] if limit else rows

    def stats(self) -> dict:
        total = self.count()
        sections = self.sections(limit=1)
        return {
            "pages": total,
            "db": str(self.db_path),
            "size_mb": round(self.db_path.stat().st_size / 1e6, 2) if self.db_path.exists() else 0.0,
            "top_section": sections[0][0] if sections else "",
        }


def print_hits(hits: list[dict], preview: int = 300) -> None:
    for i, hit in enumerate(hits, 1):
        print(f"\n{i}. {hit['breadcrumb'] or hit['title']}   [{hit['found_by']}]")
        print(f"   {hit['text'][:preview].replace(chr(10), ' ')}")
        print(f"   файл: {hit['source']}")


SEARCH_HELP = """
  Как искать:
    просто слова          — например: границы, врезание, Swarf, черновая
    точный термин         — как в интерфейсе: «Типы границ», «Диалог Инструмент»
    служебное имя диалога — например: TOOLDIALOG (contextid из справки)
    цифра (1, 2, 3…)      — открыть найденную статью целиком
    назад / меню          — выйти в главное меню (start_menu.bat)
    ?                     — эта подсказка
"""


def show_full_page(hs: "HelpSearch", hit: dict, limit: int = 6000) -> None:
    """Показывает текст найденной статьи целиком (или первые limit символов)."""
    text = hs.page_text(hit["source"]) or hit.get("text", "")
    title = hit.get("breadcrumb") or hit.get("title") or hit["source"]
    print("\n" + "=" * 62)
    print(f"  {title}")
    print(f"  Файл: {hit['source']}")
    print("=" * 62)
    print(text[:limit])
    if len(text) > limit:
        print(f"\n… (показаны первые {limit} символов из {len(text)};"
              f" полный текст — в файле выше)")


def interactive(top_k: int = 6) -> int:
    """Поиск по справке без ИИ: мгновенно, только ключевые слова.

    Управление: «назад»/«меню» — выйти в меню, «?» — подсказка,
    число после поиска — открыть найденную статью целиком.
    """
    from src.console import classify, read_line

    hs = HelpSearch()
    if not hs.pages_file.exists():
        print("Справка ещё не разобрана — искать пока нечего.")
        print()
        print("Сделай так:")
        print("  1) запусти  start_parse_help.bat      (полный разбор)")
        print("     или        start_parse_help.bat 30 (проба на 30 страницах)")
        print("  2) потом снова запусти этот поиск")
        return 2
    if hs.is_stale():
        print("Собираю индекс поиска (это быстро)...")
        hs.build()

    print("=" * 58)
    print("  ПОИСК ПО СПРАВКЕ PowerMill (без ИИ, мгновенный)")
    print(f"  Страниц в индексе: {hs.count()}")
    print("  Введи запрос. «меню» — выход, «?» — подсказка.")
    print("  После поиска цифра (1, 2, 3…) — открыть статью целиком.")
    print("=" * 58)

    last_hits: list[dict] = []
    while True:
        query = read_line("\n🔎 Что ищем: ")
        if query is None:
            return 0

        action = classify(query)
        if action in {"menu", ""}:
            print("Возврат в меню.")
            return 0
        if action == "help":
            print(SEARCH_HELP)
            continue

        # цифра = открыть статью из прошлой выдачи
        if query.strip().isdigit() and last_hits:
            number = int(query.strip())
            if 1 <= number <= len(last_hits):
                show_full_page(hs, last_hits[number - 1])
            else:
                print(f"Всего результатов {len(last_hits)} — "
                      f"введи число от 1 до {len(last_hits)}.")
            continue

        hits = hs.search(query, top_k=top_k)
        if not hits:
            print("Ничего не найдено. Попробуй один-два ключевых слова "
                  "(например: «Swarf», «границы», «врезание»).")
            print("Совет: термин можно ввести как в интерфейсе — «Типы границ».")
            continue

        last_hits = hits
        print_hits(hits)
        print(f"\n  Цифра 1-{len(hits)} — открыть статью целиком. "
              f"Или введи новый запрос. «меню» — выход.")


def main_cli() -> int:
    import sys

    from src.applog import start_log

    start_log("help_search")
    hs = HelpSearch()
    if "--rebuild" in sys.argv or hs.is_stale():
        if not hs.pages_file.exists():
            print(f"(!) Нет файла {hs.pages_file}")
            print("    Сначала разбери справку: start_parse_help.bat")
            return 2
        hs.build()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        pass
    elif "--rebuild" in sys.argv:
        print(f"Индекс собран: {hs.count()} страниц -> {hs.db_path}")
        return 0
    if args:
        print(f"Страниц в FTS-индексе: {hs.count()}")
        print_hits(hs.search(" ".join(args), top_k=5), preview=120)
    else:
        return interactive()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main_cli())
