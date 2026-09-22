"""
Векторная база знаний PowerMill: ChromaDB + SentenceTransformers (CPU).

Хранение chroma_db — только диск E (см. config.py).
"""
import chromadb
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

from config import CHROMA_DIR, CURRENT_MODE, EMBED_BATCH_SIZE, EMBEDDING_MODEL
from src.chunker import chunk_all_parsed_docs
from src.hardware import set_process_priority

COLLECTION_NAME = "powermill_knowledge"


class PowerMillVectorStore:
    """Векторное хранилище для базы знаний PowerMill."""

    def __init__(self):
        set_process_priority(CURRENT_MODE)
        self.client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        print(f"🔧 Загрузка модели эмбеддингов: {EMBEDDING_MODEL} (CPU)...")
        self.embedder = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
        print("✅ Модель загружена")

    def add_chunks(self, chunks: list[dict], batch_size: int | None = None):
        """Добавляет чанки в базу батчами."""
        batch_size = batch_size or EMBED_BATCH_SIZE
        total = len(chunks)
        print(f"📦 Загрузка {total} чанков в ChromaDB ({CHROMA_DIR})...")

        for i in tqdm(range(0, total, batch_size), desc="Эмбеддинг"):
            batch = chunks[i:i + batch_size]
            texts = [c["text"] for c in batch]
            ids = [f"{c['source']}_{c['chunk_id']}_{i + idx}" for idx, c in enumerate(batch)]
            metadatas = [{"source": c["source"]} for c in batch]

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

    def search(self, query: str, top_k: int = 4) -> list[dict]:
        """Поиск релевантных фрагментов по запросу."""
        query_embedding = self.embedder.encode(
            [query], normalize_embeddings=True
        ).tolist()

        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        hits = []
        for i in range(len(results["documents"][0])):
            hits.append({
                "text": results["documents"][0][i],
                "source": results["metadatas"][0][i]["source"],
                "distance": results["distances"][0][i],
            })
        return hits

    def rebuild(self):
        """Полная пересборка базы из всех источников."""
        try:
            self.client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        chunks = chunk_all_parsed_docs()
        if chunks:
            self.add_chunks(chunks)
        else:
            print("⚠️ Нет данных! Сначала запусти src.pdf_parser (и при наличии — video_parser).")


if __name__ == "__main__":
    PowerMillVectorStore().rebuild()
