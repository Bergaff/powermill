"""Тесты keyword-поиска (FTS5), гибридного поиска и чанкера."""
from __future__ import annotations


from src.chunker import chunk_help_page, help_header, load_help_pages
from src.help_search import HelpSearch, stem, tokenize
from src.retrieval import HybridRetriever, rrf_fuse


# --------------------------------------------------------------------------
# FTS5
# --------------------------------------------------------------------------
def test_stem_truncates_russian_endings():
    assert stem("границы") == "границ"
    assert stem("обработки") == "обработк"   # обработк* ловит обработка/обработке/обработку
    assert stem("фрезерование").startswith("фрезер")
    assert stem("abc") == "abc"          # короткие не трогаем


def test_tokenize_drops_stopwords():
    assert tokenize("как сделать чистовая обработка") == ["чистовая", "обработка"]
    assert tokenize("Swarf finishing") == ["swarf", "finishing"]
    assert tokenize("") == []


def test_help_search_finds_page_by_russian_query(parsed_pages):
    hs = HelpSearch()
    assert hs.build() > 0

    hits = hs.search("чистовая обработка по кривой", top_k=3)
    assert hits
    assert any("Чистовая обработка" in h["breadcrumb"] for h in hits)


def test_help_search_finds_exact_english_term(parsed_pages):
    hs = HelpSearch()
    hs.ensure_index()
    hits = hs.search("Swarf", top_k=3)
    assert hits
    assert "Swarf" in hits[0]["text"] or "Swarf" in hits[0]["breadcrumb"]


def test_help_search_morphology_via_prefix(parsed_pages):
    hs = HelpSearch()
    hs.ensure_index()
    # в тексте «Создайте границу», запрос — «границы»
    hits = hs.search("границы отверстий", top_k=5)
    assert hits
    assert any("границ" in h["text"].lower() for h in hits)


def test_help_search_short_terms_like_tool_codes(parsed_pages):
    hs = HelpSearch()
    hs.ensure_index()
    hits = hs.search("GUID-0002", top_k=3)
    assert hits


def test_help_search_empty_query(parsed_pages):
    hs = HelpSearch()
    hs.ensure_index()
    assert hs.search("") == []
    assert hs.search("и в на") == []       # только стоп-слова


def test_help_search_stats_and_sections(parsed_pages):
    hs = HelpSearch()
    hs.ensure_index()
    st = hs.stats()
    assert st["pages"] >= 6
    assert st["size_mb"] > 0
    assert any("Стратегии обработки" in s for s, _ in hs.sections())


# --------------------------------------------------------------------------
# Чанкер
# --------------------------------------------------------------------------
def test_chunk_help_page_adds_header_with_breadcrumb(parsed_pages):
    page = next(p for p in parsed_pages if p["title"] == "5-осевая обработка")
    chunks = chunk_help_page(page)
    assert chunks
    assert chunks[0]["text"].startswith("[Справка PowerMill · Стратегии обработки > 5-осевая")
    assert chunks[0]["source_type"] == "help"
    assert chunks[0]["breadcrumb"] == "Стратегии обработки > 5-осевая обработка"


def test_chunk_help_page_long_page_is_split(parsed_pages):
    page = dict(parsed_pages[0])
    page["text"] = "\n\n".join(f"Абзац номер {i}. " + "текст " * 60 for i in range(20))
    chunks = chunk_help_page(page)
    assert len(chunks) > 1
    assert all(c["text"].startswith("[Справка PowerMill") for c in chunks)
    # нумерация чанков сквозная внутри страницы
    assert [c["chunk_id"] for c in chunks] == list(range(len(chunks)))


def test_chunk_help_page_contexthelp_marked(parsed_pages):
    page = next(p for p in parsed_pages if p["kind"] == "contexthelp")
    chunks = chunk_help_page(page)
    assert chunks and chunks[0]["source_type"] == "help_context"


def test_load_help_pages(parsed_pages):
    pages = load_help_pages()
    assert len(pages) == 6


def test_help_header_avoids_duplicate_title():
    page = {"breadcrumb": "Начало работы > Введение", "title": "Введение", "path": "x"}
    assert help_header(page).endswith("Начало работы > Введение]")


# --------------------------------------------------------------------------
# Гибридный поиск
# --------------------------------------------------------------------------
class FakeStore:
    """Заглушка векторного хранилища: отдаёт заранее заданные попадания."""

    def __init__(self, hits):
        self.hits = hits
        self.calls: list[str] = []

    def search(self, query, top_k=4, where=None):
        self.calls.append(query)
        return self.hits[:top_k]


def _hit(source, text, distance=None, found_by="vector", strict=False):
    return {"source": source, "text": text, "title": "", "breadcrumb": "", "kind": "page",
            "source_type": "help", "distance": distance, "found_by": found_by,
            "strict": strict}


def test_rrf_fuse_merges_duplicates_and_sums_scores():
    a = [_hit("s1", "Текст один"), _hit("s2", "Текст два")]
    b = [_hit("s2", "Текст два", found_by="fts", strict=True)]
    fused = rrf_fuse(a, b)
    assert len(fused) == 2
    top = fused[0]
    assert top["source"] == "s2"
    assert top["found_by"] == "fts+vector"
    assert top["strict"] is True


def test_rrf_prefers_hit_found_by_both():
    a = [_hit("s1", "A"), _hit("s2", "B")]
    b = [_hit("s2", "B")]
    fused = rrf_fuse(a, b)
    assert fused[0]["source"] == "s2"


def test_retriever_keeps_strict_fts_even_without_vector(parsed_pages):
    hs = HelpSearch()
    hs.ensure_index()
    store = FakeStore([_hit("nowhere", "нерелевантный текст", distance=0.9)])
    retriever = HybridRetriever(store, hs, verbose=False)
    hits = retriever.search("границы по отверстиям", top_k=3)
    assert hits
    assert any(h["found_by"] == "fts" for h in hits)


def test_retriever_filters_irrelevant_vector_hits(parsed_pages):
    hs = HelpSearch()
    hs.ensure_index()
    store = FakeStore([_hit("s1", "мусор", distance=0.95)])
    retriever = HybridRetriever(store, hs, verbose=False)
    hits = retriever.search("абсолютно несуществующий термин ксилофон", top_k=3)
    assert hits == []


def test_retriever_works_without_fts():
    store = FakeStore([_hit("s1", "хороший текст про стратегию", distance=0.2)])
    retriever = HybridRetriever(store, None, verbose=False)
    hits = retriever.search("стратегия", top_k=3)
    assert len(hits) == 1
    assert hits[0]["found_by"] == "vector"


def test_retriever_survives_broken_store(parsed_pages):
    class Broken:
        def search(self, *a, **k):
            raise RuntimeError("chroma недоступна")

    hs = HelpSearch()
    hs.ensure_index()
    retriever = HybridRetriever(Broken(), hs, verbose=False)
    hits = retriever.search("чистовая обработка", top_k=3)
    assert hits  # FTS вытянул результат без векторов
