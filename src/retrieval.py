"""
Гибридный поиск по базе знаний: вектора (ChromaDB) + ключевые слова (FTS5).

Почему гибрид
-------------
  * Вектора понимают смысл («как обойти поднутрение» найдёт статью про undercut),
    но плохо ловят точные термины: `Thickness`, `HOLDER_CLEARANCE`, «D16».
  * FTS5 ловит точные термины и русскую морфологию (через усечение окончаний),
    но не понимает перефразировку.

Слияние — по Reciprocal Rank Fusion (RRF): score = Σ 1/(60 + место в списке).
Метод не требует калибровки весов и устойчив к разной природе оценок.

Дополнительно фильтр релевантности (SOURCE_MAX_DISTANCE) применяется ТОЛЬКО к
векторным попаданиям, а строгие FTS-совпадения считаются релевантными всегда —
иначе полезные точные попадания отбрасывались бы как «не по теме».
"""
from __future__ import annotations

from config import SOURCE_MAX_DISTANCE, TOP_K

RRF_K = 60


def _key(hit: dict) -> str:
    """Ключ уникальности фрагмента (страница + первые символы текста)."""
    text = (hit.get("text") or "").strip()
    return f"{hit.get('source', '?')}::{(hit.get('breadcrumb') or '')[:60]}::{text[:90]}"


def rrf_fuse(*ranked_lists: list[dict], weights: tuple[float, ...] | None = None) -> list[dict]:
    """Объединяет ранжированные списки в один по Reciprocal Rank Fusion."""
    merged: dict[str, dict] = {}
    for lst_idx, hits in enumerate(ranked_lists):
        weight = (weights[lst_idx] if weights and lst_idx < len(weights) else 1.0)
        for rank, hit in enumerate(hits):
            key = _key(hit)
            entry = merged.get(key)
            if entry is None:
                entry = dict(hit)
                entry["rrf"] = 0.0
                entry["found_by"] = set()
                merged[key] = entry
            entry["rrf"] += weight / (RRF_K + rank + 1)
            entry["found_by"].add(hit.get("found_by", "?"))
            # сохраняем лучшее (меньшее) косинусное расстояние
            dist = hit.get("distance")
            if dist is not None and (entry.get("distance") is None or dist < entry["distance"]):
                entry["distance"] = dist
            if hit.get("strict"):
                entry["strict"] = True
            if len(hit.get("text", "")) > len(entry.get("text", "")):
                entry["text"] = hit["text"]
            for field in ("title", "breadcrumb", "kind", "source_type"):
                if not entry.get(field) and hit.get(field):
                    entry[field] = hit[field]
    out = []
    for entry in merged.values():
        entry["found_by"] = "+".join(sorted(entry["found_by"]))
        out.append(entry)
    out.sort(key=lambda h: -h["rrf"])
    return out


class NullVectorStore:
    """Заглушка вместо векторной базы: её может не быть (нет библиотек или пусто).

    Нужна, чтобы чат работал по ключевым словам (FTS), а не падал: раньше
    отсутствие ChromaDB ломало запуск целиком.
    """

    available = False
    reason = "векторной базы нет"

    def search(self, query: str, **kwargs) -> list[dict]:
        return []

    def stats(self) -> dict:
        return {"total": 0, "by_type": {}, "path": "-"}


class HybridRetriever:
    """Единая точка входа для поиска по базе знаний."""

    def __init__(self, store, fts=None, use_fts: bool = True, verbose: bool = True):
        self.store = store
        self.fts = fts
        self.use_fts = use_fts and fts is not None
        if self.use_fts and verbose:
            try:
                count = fts.count()
                if count == 0:
                    self.use_fts = False
                    print("ℹ FTS-индекс пуст — работаю только на векторах "
                          "(запусти start_reindex_help.bat, чтобы включить гибридный поиск)")
                elif verbose:
                    print(f"🔎 Гибридный поиск: {count} страниц в keyword-индексе")
            except Exception:
                self.use_fts = False

    # ---------------- поиск ----------------
    def search(self, query: str, top_k: int | None = None,
               max_distance: float | None = None) -> list[dict]:
        """Гибридный поиск: возвращает фрагменты с пометками релевантности."""
        top_k = top_k or TOP_K
        max_distance = SOURCE_MAX_DISTANCE if max_distance is None else max_distance
        pool = max(top_k * 3, 8)

        vector_hits: list[dict] = []
        try:
            vector_hits = self.store.search(query, top_k=pool)
        except Exception as e:  # noqa: BLE001 — база может быть пуста/недоступна
            print(f"⚠ Векторный поиск недоступен: {e}")

        fts_hits: list[dict] = []
        query_words = len([w for w in query.split() if len(w) > 2])
        if self.use_fts and query_words >= 1:
            try:
                fts_hits = self.fts.search(query, top_k=pool)
            except Exception as e:  # noqa: BLE001
                print(f"⚠ Keyword-поиск недоступен: {e}")

        fused = rrf_fuse(vector_hits, fts_hits, weights=(1.0, 1.15))

        for hit in fused:
            dist = hit.get("distance")
            by_fts_strict = bool(hit.get("strict")) or "fts" in hit.get("found_by", "")
            hit["relevant"] = (
                (dist is not None and dist <= max_distance) or by_fts_strict
            )

        relevant = [h for h in fused if h["relevant"]]
        if not relevant:
            return []
        return relevant[:top_k]

    # ---------------- отладка ----------------
    def explain(self, query: str, top_k: int = 8) -> list[dict]:
        """Сырые результаты (для /sources): что нашлось векторами и FTS."""
        out: list[dict] = []
        try:
            out = self.store.search(query, top_k=top_k)
        except Exception as e:  # noqa: BLE001
            print(f"⚠ Векторный поиск: {e}")
        if self.use_fts:
            try:
                out = out + self.fts.search(query, top_k=top_k)
            except Exception as e:  # noqa: BLE001
                print(f"⚠ Keyword-поиск: {e}")
        return out
