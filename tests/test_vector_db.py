"""
Тесты векторной базы (пункт 6) — без ChromaDB и без моделей эмбеддингов.

Здесь проверяется то, что важно человеку: модуль не падает с трассировкой, когда
тяжёлые библиотеки не поставлены; понятно говорит, что поставить; прерванную
сборку можно продолжить (уже проиндексированное не пересчитывается); отчёт
пишется и в нём есть числа.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src import vectorstore


# --------------------------------------------------------------------------
# Заглушки: коллекция ChromaDB и модель эмбеддингов
# --------------------------------------------------------------------------
class FakeVector:
    """Что возвращает encode(): у настоящего numpy есть .tolist()."""

    def __init__(self, values):
        self.values = values

    def tolist(self):
        return self.values


class FakeEmbedder:
    def __init__(self):
        self.calls = 0

    def encode(self, texts, **kwargs):
        # encode() возвращает массив (у numpy он умеет .tolist()) — повторяем это
        self.calls += 1
        return FakeVector([[0.1, 0.2, 0.3] for _ in texts])


class FakeCollection:
    def __init__(self, ids: list[str] | None = None):
        self.ids = list(ids or [])
        self.batches: list[list[str]] = []

    def count(self):
        return len(self.ids)

    def add(self, documents, embeddings, metadatas, ids):
        self.batches.append(list(ids))
        self.ids.extend(ids)

    def get(self, limit=None, offset=0, include=None):
        page = self.ids[offset:offset + (limit or len(self.ids))]
        return {"ids": page, "metadatas": [{} for _ in page]}


class FakeClient:
    def __init__(self, collection: FakeCollection):
        self._collection = collection
        self.deleted: list[str] = []

    def delete_collection(self, name):
        self.deleted.append(name)
        self._collection.ids = []

    def get_or_create_collection(self, name, metadata=None):
        return self._collection


def make_store(collection: FakeCollection | None = None) -> vectorstore.PowerMillVectorStore:
    """Хранилище без ChromaDB: только то, что нужно для проверки логики."""
    store = object.__new__(vectorstore.PowerMillVectorStore)
    store.collection = collection or FakeCollection()
    store.client = FakeClient(store.collection)
    store.embedder = FakeEmbedder()
    return store


def chunk(index: int, source: str = "powermill_help") -> dict:
    return {"text": f"текст {index}", "source": source, "chunk_id": index,
            "source_type": "help", "title": "t", "breadcrumb": "b",
            "kind": "text"}


# --------------------------------------------------------------------------
# Библиотеки: понятное сообщение вместо трассировки
# --------------------------------------------------------------------------
def test_module_imports_without_heavy_libraries():
    """chromadb и sentence-transformers не стоят — модуль всё равно работает."""
    assert hasattr(vectorstore, "main")
    assert hasattr(vectorstore, "missing_libraries")


def test_missing_library_message_names_what_to_install():
    error = vectorstore.MissingLibrary(["chromadb", "sentence-transformers"])
    text = str(error)
    assert "chromadb" in text
    assert "43" in text                       # куда идти за библиотеками


def test_check_reports_missing_libraries_instead_of_crashing(monkeypatch):
    monkeypatch.setattr(vectorstore, "missing_libraries",
                        lambda: ["chromadb", "sentence-transformers"])
    state = vectorstore.check(quiet=True)
    assert state["missing_libraries"] == ["chromadb", "sentence-transformers"]
    assert "43" in state["note"]


def test_main_check_returns_code_two_without_libraries(monkeypatch, capsys):
    monkeypatch.setattr(vectorstore, "missing_libraries", lambda: ["chromadb"])
    code = vectorstore.main(["--check"])
    assert code == 2                          # батник скажет «нет библиотек»
    assert "43" in capsys.readouterr().out


# --------------------------------------------------------------------------
# Возобновление: уже проиндексированное не пересчитывается
# --------------------------------------------------------------------------
def test_existing_ids_reads_the_whole_base_by_pages():
    store = make_store(FakeCollection([f"id-{i}" for i in range(7)]))
    assert store.existing_ids(page=3) == {f"id-{i}" for i in range(7)}


def test_add_chunks_skips_what_is_already_there():
    chunks = [chunk(i) for i in range(3)]
    first_ids = ["help:powermill_help:0"]       # первый кусок уже в базе
    store = make_store(FakeCollection(first_ids))
    added = store.add_chunks(chunks, skip_ids=set(first_ids), quiet=True)
    assert added == 2
    assert store.collection.ids == first_ids + [
        "help:powermill_help:1", "help:powermill_help:2"]


def test_ids_do_not_depend_on_the_order_of_documents():
    """Идентификатор куска — источник и номер: добор не зависит от порядка."""
    store = make_store()
    store.add_chunks([chunk(0, "page-a"), chunk(1, "page-a")], quiet=True)
    first = list(store.collection.batches[-1])
    store.add_chunks([chunk(0, "page-b")], quiet=True)
    # куски первой страницы остались теми же, даже если список документов рос
    assert first == ["help:page-a:0", "help:page-a:1"]
    assert store.collection.batches[-1] == ["help:page-b:0"]


def test_add_chunks_adds_everything_when_base_is_empty():
    store = make_store()
    assert store.add_chunks([chunk(0), chunk(1)], quiet=True) == 2
    assert len(store.collection.batches) == 1


def test_rebuild_resume_keeps_old_records(monkeypatch, tmp_path):
    """Прерванная сборка продолжается: старое не удаляется, новое добавляется."""
    already = ["help:powermill_help:0"]
    store = make_store(FakeCollection(already))
    monkeypatch.setattr(vectorstore, "chunk_all_parsed_docs",
                        lambda: [chunk(0), chunk(1)])
    monkeypatch.setattr(vectorstore, "REPORT_FILE",
                        tmp_path / "vector_db_report.txt")

    stats = store.rebuild(build_fts=False, resume=True, quiet=True)
    assert store.client.deleted == []                 # старую базу не трогали
    assert stats["already"] == 1
    assert stats["added"] == 1
    assert stats["final_count"] == 2
    text = (tmp_path / "vector_db_report.txt").read_text(encoding="utf-8")
    assert "Добавлено сейчас:    1" in text
    assert "Записей в базе:      2" in text


def test_rebuild_from_scratch_deletes_old_collection(monkeypatch, tmp_path):
    store = make_store(FakeCollection(["старое:1"]))
    monkeypatch.setattr(vectorstore, "chunk_all_parsed_docs", lambda: [chunk(0)])
    monkeypatch.setattr(vectorstore, "REPORT_FILE",
                        tmp_path / "vector_db_report.txt")

    stats = store.rebuild(build_fts=False, resume=False, quiet=True)
    assert store.client.deleted == [vectorstore.COLLECTION_NAME]
    assert stats["mode"] == "с нуля"
    assert stats["final_count"] == 1


def test_rebuild_says_what_to_do_when_nothing_parsed(monkeypatch, tmp_path,
                                                    capsys):
    store = make_store()
    monkeypatch.setattr(vectorstore, "chunk_all_parsed_docs", lambda: [])
    monkeypatch.setattr(vectorstore, "REPORT_FILE",
                        tmp_path / "vector_db_report.txt")
    stats = store.rebuild(build_fts=False, quiet=True)
    assert stats["chunks_total"] == 0
    out = capsys.readouterr().out
    assert "пункт 4" in out                            # отправляем разбирать справку


def test_limit_makes_a_trial_run(monkeypatch, tmp_path):
    store = make_store()
    monkeypatch.setattr(vectorstore, "chunk_all_parsed_docs",
                        lambda: [chunk(i) for i in range(10)])
    monkeypatch.setattr(vectorstore, "REPORT_FILE",
                        tmp_path / "vector_db_report.txt")
    stats = store.rebuild(build_fts=False, limit=4, quiet=True)
    assert stats["chunks_total"] == 4
    assert stats["final_count"] == 4


def test_progress_line_shows_numbers(capsys):
    store = make_store()
    store._progress(50, 100, 20, 10.0, quiet=False)
    out = capsys.readouterr().out
    assert "50/100" in out and "осталось" in out


def test_report_written_even_for_empty_base(tmp_path, monkeypatch):
    store = make_store()
    monkeypatch.setattr(vectorstore, "REPORT_FILE", tmp_path / "nested" /
                        "vector_db_report.txt")
    path = store.write_report({"chunks_total": 0, "mode": "добор"},
                              note="нет данных для индексации")
    text = path.read_text(encoding="utf-8")
    assert "ВЕКТОРНАЯ БАЗА" in text
    assert "нет данных для индексации" in text


# --------------------------------------------------------------------------
# Чат работает и без векторной базы (только по ключевым словам)
# --------------------------------------------------------------------------
def test_null_store_returns_nothing_but_does_not_break(monkeypatch):
    from src.retrieval import HybridRetriever, NullVectorStore

    class FakeFts:
        def count(self):
            return 3

        def search(self, query, top_k=5):
            return [{"text": "как фрезеровать", "source": "page-1", "title": "t",
                     "breadcrumb": "", "kind": "text", "source_type": "help",
                     "distance": 0.1, "found_by": "fts", "strict": True}]

    retriever = HybridRetriever(NullVectorStore(), FakeFts(), verbose=False)
    hits = retriever.search("фрезеровать", top_k=3)
    assert hits and hits[0]["source"] == "page-1"
    assert NullVectorStore().stats()["total"] == 0


def test_chat_starts_without_vector_library(monkeypatch, capsys):
    """Нет chromadb — чат всё равно поднимается и говорит, что делать."""
    from src import rag, vectorstore

    def boom(self, load_embedder=True):
        raise vectorstore.MissingLibrary(["chromadb", "sentence-transformers"])

    monkeypatch.setattr(vectorstore.PowerMillVectorStore, "__init__", boom)
    ai = rag.PowerMillAI(load_fts=False, verbose=True)
    out = capsys.readouterr().out
    assert "Векторного поиска нет" in out
    assert "43" in out                                   # куда идти за библиотеками
    assert ai.store.available is False
    assert "нет" in ai.stats()
    assert "пунктом 6" in ai.stats()                      # как собрать базу
