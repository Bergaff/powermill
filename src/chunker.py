"""
Разбивка текстов (справка, PDF, видео, макросы) на чанки для векторной базы.

Особенность: страницы справки чанкуются ПО ОТДЕЛЬНОСТИ, и в каждый чанк
дописывается «шапка» с разделом и заголовком:

    [Справка PowerMill · Стратегии обработки > Чистовая обработка по кривой]

Это критично для качества: без шапки чанк из середины статьи («нажмите
кнопку ОК») не найти ни по вектору, ни по ключевым словам.
"""
from __future__ import annotations

import json
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    HELP_FILES_DIR,
    MACRO_DIR,
    OUTPUT_DIR,
)

PAGES_FILE = OUTPUT_DIR / "help_pages.jsonl"
LEGACY_HTML_FILE = OUTPUT_DIR / "parsed_html.txt"
PDF_FILE = OUTPUT_DIR / "parsed_docs.txt"

MIN_CHUNK_CHARS = 30


def create_splitter() -> RecursiveCharacterTextSplitter:
    """Сплиттер под техническую документацию (Markdown-подобная разметка)."""
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n## ", "\n### ", "\n\n", "\n", ". ", " "],
        length_function=len,
    )


def chunk_text(text: str, source: str = "unknown") -> list[dict]:
    """Разбивает текст на чанки с метаданными."""
    raw_chunks = create_splitter().split_text(text)
    return [
        {"text": chunk.strip(), "source": source, "chunk_id": i, "title": "",
         "breadcrumb": "", "kind": "text", "source_type": "text"}
        for i, chunk in enumerate(raw_chunks)
        if len(chunk.strip()) > MIN_CHUNK_CHARS
    ]


def load_help_pages(path: Path | None = None) -> list[dict]:
    """Читает output/help_pages.jsonl (пишет src.html_parser)."""
    path = Path(path or PAGES_FILE)
    if not path.exists():
        return []
    pages: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pages.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return pages


def help_header(page: dict) -> str:
    """Шапка чанка: раздел + заголовок страницы."""
    crumb = page.get("breadcrumb") or page.get("title") or ""
    title = page.get("title") or ""
    if crumb and title and not crumb.rstrip().endswith(title):
        crumb = f"{crumb} > {title}"
    return f"[Справка PowerMill · {crumb or page.get('path', '')}]"


def chunk_help_page(page: dict, splitter: RecursiveCharacterTextSplitter | None = None) -> list[dict]:
    """Страница справки -> чанки с шапкой и метаданными."""
    splitter = splitter or create_splitter()
    body = (page.get("text") or "").strip()
    if not body:
        return []

    source = page.get("source", page.get("path", "help"))
    header = help_header(page)
    kind = page.get("kind", "page")
    source_type = "help_context" if kind == "contexthelp" else "help"

    if len(body) <= CHUNK_SIZE:
        parts = [body]
    else:
        parts = splitter.split_text(body)

    chunks: list[dict] = []
    for i, part in enumerate(parts):
        text = f"{header}\n{part.strip()}"
        if len(text) < MIN_CHUNK_CHARS:
            continue
        chunks.append({
            "text": text,
            "source": source,
            "chunk_id": i,
            "title": page.get("title", ""),
            "breadcrumb": page.get("breadcrumb", ""),
            "kind": kind,
            "source_type": source_type,
            "page_order": page.get("order", 10_000),
        })
    return chunks


def _chunks_from_legacy_txt(path: Path, source: str, source_type: str = "help") -> list[dict]:
    """Старый формат (parsed_html.txt): чанки без заголовков."""
    if not path.exists():
        return []
    chunks = chunk_text(path.read_text(encoding="utf-8"), source=source)
    for c in chunks:
        c["source_type"] = source_type
    return chunks


def chunk_all_parsed_docs() -> list[dict]:
    """Собирает чанки из всех источников: справка, PDF, транскрипты, макросы."""
    all_chunks: list[dict] = []

    # 1. Оффлайн-справка PowerMill (основной источник знаний)
    pages = load_help_pages()
    if pages:
        splitter = create_splitter()
        help_chunks: list[dict] = []
        for page in pages:
            help_chunks.extend(chunk_help_page(page, splitter))
        all_chunks.extend(help_chunks)
        kinds: dict[str, int] = {}
        for c in help_chunks:
            kinds[c["source_type"]] = kinds.get(c["source_type"], 0) + 1
        print(f"📘 Справка HTML: {len(pages)} страниц -> {len(help_chunks)} чанков {kinds}")
    else:
        legacy = _chunks_from_legacy_txt(LEGACY_HTML_FILE, "powermill_help")
        all_chunks.extend(legacy)
        if legacy:
            print(f"📘 HTML-справка (старый формат): {len(legacy)} чанков")

    # 2. Распарсенная документация PDF
    if PDF_FILE.exists():
        chunks = chunk_text(PDF_FILE.read_text(encoding="utf-8"), source="powermill_docs")
        for c in chunks:
            c["source_type"] = "pdf"
        all_chunks.extend(chunks)
        print(f"📄 PDF-документация: {len(chunks)} чанков")

    # 3. Транскрипции видео
    for txt_file in sorted(OUTPUT_DIR.glob("*_transcript.txt")):
        chunks = chunk_text(
            txt_file.read_text(encoding="utf-8"),
            source=f"video:{txt_file.stem}",
        )
        for c in chunks:
            c["source_type"] = "video"
        all_chunks.extend(chunks)
        print(f"🎬 {txt_file.name}: {len(chunks)} чанков")

    # 4. PML-макросы (каждый файл — отдельный чанк)
    macro_files = sorted(MACRO_DIR.glob("*.mac"))
    for macro_file in macro_files:
        content = macro_file.read_text(encoding="utf-8", errors="ignore")
        all_chunks.append({
            "text": f"PML Macro ({macro_file.name}):\n{content}",
            "source": f"macro:{macro_file.name}",
            "chunk_id": 0,
            "title": macro_file.name,
            "breadcrumb": "Макросы PML",
            "kind": "macro",
            "source_type": "macro",
        })
    if macro_files:
        print(f"⚙️ Макросы: {len(macro_files)} чанков")

    print(f"\n✅ Итого: {len(all_chunks)} чанков")
    return all_chunks


if __name__ == "__main__":
    chunks = chunk_all_parsed_docs()
    for c in chunks[:3]:
        print("-" * 60)
        print(c["text"][:300])
