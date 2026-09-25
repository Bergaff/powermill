"""
Векторная база знаний PowerMill: ChromaDB + SentenceTransformers (CPU).

Что здесь главное
-----------------
* **Тяжёлые библиотеки подключаются только при работе.** `chromadb` и
  `sentence-transformers` весят гигабайты и ставятся отдельно (пункт 43 с
  ключом `--all`). Если их нет, модуль всё равно импортируется и объясняет
  человеку, что делать, — вместо трассировки `ModuleNotFoundError`.
* **Индексацию можно прервать и продолжить.** Считается не «всё с нуля», а
  «чего ещё нет в базе»: при повторном запуске уже проиндексированные куски
  пропускаются, поэтому ночной запуск можно безопасно прерывать.
* **Отчёт пишется всегда** — `output\\vector_db_report.txt`: сколько кусков
  всего, сколько уже было, сколько добавили, что в базе сейчас.

Запуск (обычно из пункта 6 меню)::

    python -m src.vectorstore              # добрать недостающее
    python -m src.vectorstore --rebuild    # пересобрать с нуля
    python -m src.vectorstore --check      # только посмотреть, что есть
    python -m src.vectorstore --limit 200  # пробный прогон на 200 кусках
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from config import CHROMA_DIR, CURRENT_MODE, EMBED_BATCH_SIZE, EMBEDDING_MODEL
from src.chunker import chunk_all_parsed_docs
from src.hardware import set_process_priority

COLLECTION_NAME = "powermill_knowledge"
REPORT_FILE = Path(CHROMA_DIR).parent / "output" / "vector_db_report.txt"

# Что нужно для векторной базы: имя пакета -> модуль для проверки и зачем
HEAVY_PACKAGES = (
    ("chromadb", "chromadb", "хранение векторов и поиск по ним"),
    ("sentence-transformers", "sentence_transformers",
     "превращение текста в векторы (эмбеддинги)"),
    ("tqdm", "tqdm", "полоска прогресса (необязательно)"),
)


class MissingLibrary(RuntimeError):
    """Нет библиотеки для векторной базы — с понятным текстом, что поставить."""

    def __init__(self, packages: list[str]):
        self.packages = packages
        super().__init__(
            "Для векторной базы нужны библиотеки: " + ", ".join(packages) +
            ".\nПоставить: пункт 43 меню с ключом --all "
            "(или кнопка «Установить недостающее» в окне приложения).")


def missing_libraries() -> list[str]:
    """Чего не хватает для векторной базы (tqdm — не считается обязательным)."""
    from src import deps

    lack = [package for package, module, _purpose in HEAVY_PACKAGES[:2]
            if not deps.module_available(module)]
    return lack


def _fmt_time(seconds: float) -> str:
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f"{seconds} с"
    minutes, rest = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} мин {rest:02d} с"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} ч {minutes:02d} мин"


class PowerMillVectorStore:
    """Векторное хранилище для базы знаний PowerMill."""

    def __init__(self, load_embedder: bool = True):
        lack = missing_libraries()
        if lack:
            raise MissingLibrary(lack)
        import chromadb                                    # noqa: PLC0415

        set_process_priority(CURRENT_MODE)
        self.client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self.embedder: SentenceTransformer | None = None
        if load_embedder:
            from sentence_transformers import SentenceTransformer   # noqa: PLC0415

            print(f"🔧 Загрузка модели эмбеддингов: {EMBEDDING_MODEL} (CPU)...")
            print("   (в первый раз модель скачивается, это может занять время)")
            self.embedder = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
            print("✅ Модель загружена")

    # ---------------- запись ----------------
    def existing_ids(self, page: int = 5000) -> set[str]:
        """Что уже лежит в базе. По страницам, чтобы не тянуть всё в память."""
        known: set[str] = set()
        offset = 0
        while True:
            try:
                got = self.collection.get(limit=page, offset=offset, include=[])
            except TypeError:
                got = self.collection.get(limit=page, offset=offset,
                                          include=["metadatas"])
            except Exception:                                 # noqa: BLE001
                break
            ids = got.get("ids") or []
            if not ids:
                break
            known.update(ids)
            offset += len(ids)
            if len(ids) < page:
                break
        return known

    def add_chunks(self, chunks: list[dict], batch_size: int | None = None,
                   skip_ids: set[str] | None = None, quiet: bool = False):
        """Добавляет чанки в базу батчами (метаданные: раздел, тип, заголовок).

        `skip_ids` — то, что уже в базе: пропускаем, чтобы прерванную сборку
        можно было продолжить, а не начинать заново.
        """
        if self.embedder is None:
            raise RuntimeError("Эмбеддер не загружен: PowerMillVectorStore(load_embedder=True)")
        batch_size = batch_size or EMBED_BATCH_SIZE
        skip_ids = skip_ids or set()
        total = len(chunks)
        added = 0
        started = time.time()
        if not quiet:
            print(f"📦 Загрузка {total} чанков в ChromaDB ({CHROMA_DIR})...")

        for i in range(0, total, batch_size):
            batch = chunks[i:i + batch_size]
            texts = [c["text"] for c in batch]
            # Идентификатор куска — «источник + номер внутри источника». Он не
            # зависит от порядка батчей и от других документов, поэтому добор
            # после прерывания точно узнаёт, что уже проиндексировано
            # (раньше в номер входила позиция в общем списке — при добавлении
            # новых страниц всё «съезжало» и куски дублировались).
            ids = [
                f"{c.get('source_type', 'doc')}:{c['source']}:{c.get('chunk_id', 0)}"
                for c in batch
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
            # Что уже проиндексировано — выбрасываем из батча (возобновление
            # прерванной сборки: считаем только новое).
            keep = [idx for idx, item in enumerate(ids) if item not in skip_ids]
            if not keep:
                self._progress(i + len(batch), total, added, started, quiet)
                continue
            batch = [batch[idx] for idx in keep]
            ids = [ids[idx] for idx in keep]
            texts = [texts[idx] for idx in keep]
            metadatas = [metadatas[idx] for idx in keep]

            embeddings = self.embedder.encode(
                texts, show_progress_bar=False, normalize_embeddings=True
            ).tolist()

            self.collection.add(
                documents=texts,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids,
            )
            added += len(ids)
            self._progress(i + len(batch), total, added, started, quiet)

        if not quiet:
            print(f"✅ Добавлено {added} записей. Всего в базе: "
                  f"{self.collection.count()}")
        return added

    def _progress(self, done: int, total: int, added: int, started: float,
                  quiet: bool) -> None:
        """Показывает, как идёт сборка: без tqdm, чтобы не зависеть от него."""
        if quiet or not total:
            return
        share = done / total
        spent = time.time() - started
        # Печатаем один раз на батч (вызывающий передаёт сюда конец батча) —
        # этого достаточно и по времени, и по объёму вывода.
        left = (spent / share - spent) if share > 0.01 else 0.0
        line = (f"    {done}/{total} ({share * 100:.0f}%), добавлено {added}, "
                f"прошло {_fmt_time(spent)}" +
                (f", осталось ~{_fmt_time(left)}" if left else ""))
        print(line, flush=True)

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
    def rebuild(self, build_fts: bool = True, resume: bool = False,
                limit: int | None = None, quiet: bool = False) -> dict:
        """Собрать базу из всех источников.

        `resume=True` (обычный режим пункта 6) — добавить только то, чего в базе
        ещё нет: прерванную сборку можно продолжить, не теряя сделанного.
        `resume=False` — пересобрать с нуля (сначала ГОТОВЯТСЯ чанки, и только
        потом удаляется старая коллекция, чтобы при сбое база не опустела).
        """
        chunks = chunk_all_parsed_docs()
        if limit:
            chunks = chunks[:limit]
        stats = {"chunks_total": len(chunks), "already": 0, "added": 0,
                 "final_count": 0, "fts": "-", "mode": "добор" if resume else "с нуля"}
        if not chunks:
            print("⚠️ Данных для векторной базы нет.")
            print("   Сначала разбери справку PowerMill — пункт 4 меню "
                  "(и, по желанию, PDF и видео — пункт 7).")
            self.write_report(stats, note="нет данных для индексации")
            return stats

        skip: set[str] = set()
        if resume and self.collection.count():
            skip = self.existing_ids()
            stats["already"] = len(skip)
            print(f"Уже в базе: {len(skip)} записей — их пропускаю "
                  f"(прерванную сборку можно продолжать).")
        else:
            try:
                self.client.delete_collection(COLLECTION_NAME)
            except Exception:                                 # noqa: BLE001
                pass
            self.collection = self.client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )

        added = self.add_chunks(chunks, skip_ids=skip, quiet=quiet)
        stats["added"] = added or 0
        stats["final_count"] = self.collection.count()

        if build_fts:
            from src.help_search import HelpSearch

            hs = HelpSearch()
            if hs.pages_file.exists():
                count = hs.build(verbose=not quiet)
                stats["fts"] = f"{count} страниц"
            else:
                stats["fts"] = "нет разобранной справки"

        self.write_report(stats)
        print()
        print(f"🎉 Векторная база готова: {stats['final_count']} записей "
              f"({CHROMA_DIR})")
        return stats

    def write_report(self, stats: dict, note: str = "") -> Path:
        """Отчёт: его присылают в чат, если что-то пошло не так."""
        lines = [
            "=" * 60,
            "  ВЕКТОРНАЯ БАЗА (ChromaDB) — пункт 6",
            "=" * 60,
            f"  Проверено: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"  Папка базы: {CHROMA_DIR}",
            f"  Режим:      {stats.get('mode', '-')}",
            f"  Модель:     {EMBEDDING_MODEL}",
            "",
            f"  Кусков всего:        {stats.get('chunks_total', 0)}",
            f"  Уже было в базе:     {stats.get('already', 0)}",
            f"  Добавлено сейчас:    {stats.get('added', 0)}",
            f"  Записей в базе:      {stats.get('final_count', 0)}",
            f"  Поиск по справке:    {stats.get('fts', '-')}",
        ]
        if note:
            lines += ["", "  Примечание: " + note]
        lines += [
            "",
            "Дальше:",
            "  • вопросы по справке: start_work_chat.bat (пункт 1) или окно приложения;",
            "  • если справку разбирали заново (пункт 4) — запусти этот пункт",
            "    с ключом --rebuild, иначе в базе останется старый текст кусков;",
            "  • сборку можно прерывать: следующий запуск продолжит с места",
            "    остановки (уже проиндексированное не считается заново).",
        ]
        text = "\n".join(lines) + "\n"
        try:
            REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
            REPORT_FILE.write_text(text, encoding="utf-8")
        except OSError:
            pass
        return REPORT_FILE


def check(quiet: bool = False) -> dict:
    """Что уже есть: библиотеки, папка базы, сколько записей."""
    from src import deps

    stats: dict = {
        "missing_libraries": missing_libraries(),
        "chroma_dir": str(CHROMA_DIR),
        "chroma_dir_exists": Path(CHROMA_DIR).exists(),
        "collection_count": 0,
        "report": str(REPORT_FILE),
        "report_exists": REPORT_FILE.exists(),
        "note": "",
    }
    for package, module, purpose in HEAVY_PACKAGES:
        ok = deps.module_available(module)
        if not quiet:
            mark = "✔" if ok else ("✘" if package != "tqdm" else "•")
            print(f"  {mark} {package} — {purpose}")
    if stats["missing_libraries"]:
        stats["note"] = ("Нет библиотек: " + ", ".join(stats["missing_libraries"]) +
                         " — поставить пунктом 43 меню с --all.")
        return stats
    try:
        store = PowerMillVectorStore(load_embedder=False)
        stats["collection_count"] = store.collection.count()
    except Exception as error:                                # noqa: BLE001
        stats["note"] = f"база не открылась: {error}"
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Векторная база знаний PowerMill (пункт 6)")
    parser.add_argument("--check", action="store_true",
                        help="только показать состояние, ничего не собирать")
    parser.add_argument("--rebuild", action="store_true",
                        help="пересобрать с нуля (по умолчанию — добор)")
    parser.add_argument("--limit", type=int, default=0,
                        help="сделать только первые N кусков (проба)")
    parser.add_argument("--no-fts", action="store_true",
                        help="не пересобирать keyword-поиск по справке")
    parser.add_argument("--quiet", action="store_true", help="меньше вывода")
    args = parser.parse_args(argv)

    print("=" * 60)
    print("  ВЕКТОРНАЯ БАЗА ЗНАНИЙ PowerMill (ChromaDB)")
    print("=" * 60)
    print(f"  Папка базы: {CHROMA_DIR}")
    print(f"  Отчёт:      {REPORT_FILE}")
    print()
    print("Библиотеки:")
    state = check()
    print()
    if state["missing_libraries"]:
        print("[!] " + state["note"])
        print("    Дальше: start_menu.bat -> 43 (доставить библиотеки, ключ --all)")
        return 2
    if state.get("note"):
        print("[!] " + state["note"])

    if args.check:
        print(f"Записей в базе: {state['collection_count']}")
        if not state["chroma_dir_exists"]:
            print("Папки базы ещё нет — она появится при первой сборке.")
        return 0

    store = PowerMillVectorStore()
    stats = store.rebuild(build_fts=not args.no_fts, resume=not args.rebuild,
                          limit=args.limit or None, quiet=args.quiet)
    print(f"📝 Отчёт: {REPORT_FILE}")
    if not stats.get("chunks_total"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
