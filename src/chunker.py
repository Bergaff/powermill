"""
Разбивка текстов (PDF, видео, макросы) на чанки для векторной базы.
"""
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    MACRO_DIR,
    OUTPUT_DIR,
)


def create_splitter() -> RecursiveCharacterTextSplitter:
    """Сплиттер под техническую документацию."""
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
        {"text": chunk.strip(), "source": source, "chunk_id": i}
        for i, chunk in enumerate(raw_chunks)
        if len(chunk.strip()) > 30
    ]


def chunk_all_parsed_docs() -> list[dict]:
    """Собирает чанки из всех источников: PDF, транскрипты видео, макросы."""
    all_chunks: list[dict] = []

    # 1. Распарсенная документация PDF
    pdf_file = OUTPUT_DIR / "parsed_docs.txt"
    if pdf_file.exists():
        chunks = chunk_text(pdf_file.read_text(encoding="utf-8"), source="powermill_docs")
        all_chunks.extend(chunks)
        print(f"📄 PDF-документация: {len(chunks)} чанков")

    # 1b. Локальная HTML-справка PowerMill (стратегии, резцы, PML...)
    html_file = OUTPUT_DIR / "parsed_html.txt"
    if html_file.exists():
        chunks = chunk_text(html_file.read_text(encoding="utf-8"), source="powermill_help")
        all_chunks.extend(chunks)
        print(f"📘 HTML-справка: {len(chunks)} чанков")

    # 2. Транскрипции видео
    for txt_file in sorted(OUTPUT_DIR.glob("*_transcript.txt")):
        chunks = chunk_text(
            txt_file.read_text(encoding="utf-8"),
            source=f"video:{txt_file.stem}",
        )
        all_chunks.extend(chunks)
        print(f"🎬 {txt_file.name}: {len(chunks)} чанков")

    # 3. PML-макросы (каждый файл — отдельный чанк)
    macro_files = sorted(MACRO_DIR.glob("*.mac"))
    for macro_file in macro_files:
        content = macro_file.read_text(encoding="utf-8", errors="ignore")
        all_chunks.append({
            "text": f"PML Macro ({macro_file.name}):\n{content}",
            "source": f"macro:{macro_file.name}",
            "chunk_id": 0,
        })
    if macro_files:
        print(f"⚙️ Макросы: {len(macro_files)} чанков")

    print(f"\n✅ Итого: {len(all_chunks)} чанков")
    return all_chunks


if __name__ == "__main__":
    chunk_all_parsed_docs()
