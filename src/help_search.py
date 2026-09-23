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
SCHEMA_VERSION = 2

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
                "source, title, section, kind UNINDEXED, body, "
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
                    print(f"⚠ Нет {self.pages_file} — сначала запусти src.html_parser")
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
                p.get("kind", "page"),
                p.get("text", ""),
            )
            for p in pages
            if p.get("text", "").strip()
        ]
        conn.executemany(
            "INSERT INTO pages (source, title, section, kind, body) VALUES (?,?,?,?,?)",
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
            "snippet(pages, 4, '«', '»', ' … ', 18) AS snip, bm25(pages) AS rank "
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


if __name__ == "__main__":
    import sys

    hs = HelpSearch()
    if "--rebuild" in sys.argv or hs.is_stale():
        hs.build()
    print(f"Страниц в FTS-индексе: {hs.count()}")
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        for hit in hs.search(" ".join(sys.argv[1:]), top_k=5):
            print(f"  {hit['score']:8.2f}  {hit['breadcrumb'][:70]}\n      {hit['text'][:110]}")
