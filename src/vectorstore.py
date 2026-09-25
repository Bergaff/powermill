"""
Векторная база знаний PowerMill: ChromaDB + SentenceTransformers (CPU).

Хранение chroma_db — только диск E (см. config.py).
Первый запуск после установки справки: python -m src.vectorstore  (полная
пересборка базы + FTS-индекс keyword-поиска).
"""
from __future__ import annotations

import chromadb
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

from config import CHROMA_DIR, CURRENT_MODE, EMBED_BATCH_SIZE, EMBEDDING_MODEL
from src.chunker import chunk_all_parsed_docs
from src.hardware import set_process_priority

COLLECTION_NAME = "powermill_knowledge"


class PowerMillVectorStore:
    """Векторное хранилище для базы знаний PowerMill."""

    def __init__(self, load_embedder: bool = True):
        set_process_priority(CURRENT_MODE)
        self.client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self.embedder: SentenceTransformer | None = None
        if load_embedder:
            print(f"🔧 Загрузка модели эмбеддингов: {EMBEDDING_MODEL} (CPU)...")
            self.embedder = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
            print("✅ Модель загружена")

    # ---------------- запись ----------------
    def add_chunks(self, chunks: list[dict], batch_size: int | None = None):
        """Добавляет чанки в базу батчами (с метаданными: раздел, тип, заголовок)."""
        if self.embedder is None:
            raise RuntimeError("Эмбеддер не загружен: PowerMillVectorStore(load_embedder=True)")
        batch_size = batch_size or EMBED_BATCH_SIZE
        total = len(chunks)
        print(f"📦 Загрузка {total} чанков в ChromaDB ({CHROMA_DIR})...")

        for i in tqdm(range(0, total, batch_size), desc="Эмбеддинг"):
            batch = chunks[i:i + batch_size]
            texts = [c["text"] for c in batch]
            ids = [
                f"{c.get('source_type', 'doc')}:{c['source']}:{c.get('chunk_id', 0)}:{i + idx}"
                for idx, c in enumerate(batch)
            ]
            metadatas = [
                {
                    "source": c["source"],
                    "title": c.get("title") or "",
                    "breadcrumb": c.get("breadcrumb") or "",
                    "kind": c.get("kind") or "text",
                    "source_type": c.get("source_type") or "text",
                }
                for c in batch
            ]

            embeddings = self.embedder.encode(
                texts, show_progress_bar=False, normalize_embeddings=True
            ).tolist()

            self.collection.add(
                documents=texts,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids,
            )

        print(f"✅ Загружено. Всего записей в базе: {self.collection.count()}")

    # ---------------- чтение ----------------
    def search(self, query: str, top_k: int = 4, where: dict | None = None) -> list[dict]:
        """Поиск релевантных фрагментов по запросу (косинусное расстояние)."""
        if self.embedder is None:
            raise RuntimeError("Эмбеддер не загружен")
        query_embedding = self.embedder.encode(
            [query], normalize_embeddings=True
        ).tolist()

        kwargs = dict(
            query_embeddings=query_embedding,
            n_results=max(1, min(top_k, max(self.collection.count(), 1))),
            include=["documents", "metadatas", "distances"],
        )
        if where:
            kwargs["where"] = where

        results = self.collection.query(**kwargs)

        hits: list[dict] = []
        docs = results.get("documents") or [[]]
        metas = results.get("metadatas") or [[]]
        dists = results.get("distances") or [[]]
        for i in range(len(docs[0])):
            meta = metas[0][i] or {}
            hits.append({
                "text": docs[0][i],
                "source": meta.get("source", "?"),
                "title": meta.get("title", ""),
                "breadcrumb": meta.get("breadcrumb", ""),
                "kind": meta.get("kind", "text"),
                "source_type": meta.get("source_type", "text"),
                "distance": dists[0][i],
                "found_by": "vector",
            })
        return hits

    def stats(self) -> dict:
        """Сколько всего записей и из каких источников."""
        total = self.collection.count()
        by_type: dict[str, int] = {}
        if total:
            got = self.collection.get(include=["metadatas"], limit=min(total, 50_000))
            for meta in got.get("metadatas") or []:
                st = (meta or {}).get("source_type", "?")
                by_type[st] = by_type.get(st, 0) + 1
        return {"total": total, "by_type": by_type, "path": str(CHROMA_DIR)}

    # ---------------- пересборка ----------------
    def rebuild(self, build_fts: bool = True):
        """Полная пересборка базы из всех источников.

        Сначала ГОТОВЯТСЯ чанки, и только потом удаляется старая коллекция —
        чтобы при сбое/прерывании база не осталась пустой.
        """
        chunks = chunk_all_parsed_docs()
        if not chunks:
            print(
                "⚠️ Нет данных для пересборки! Сначала запусти "
                "start_reindex_help.bat (или start_night_indexing.bat)."
            )
            return

        try:
            self.client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self.add_chunks(chunks)

        if build_fts:
            from src.help_search import HelpSearch

            hs = HelpSearch()
            if hs.pages_file.exists():
                hs.build()

        print("\n🎉 База знаний готова. Теперь: start_work_chat.bat")


if __name__ == "__main__":
    PowerMillVectorStore().rebuild()
