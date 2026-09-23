"""
Парсер PDF-документации PowerMill: PDF -> текст -> output/parsed_docs.txt
"""
import re
from pathlib import Path

try:
    import pymupdf as fitz  # PyMuPDF >= 1.24
except ImportError:  # старый alias
    import fitz
from tqdm import tqdm

from config import OUTPUT_DIR, PDF_DIR


def clean_text(text: str) -> str:
    """Очистка типичного мусора из технических PDF."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"^\s*\d+\s*$", "", text, flags=re.MULTILINE)  # номера страниц
    text = re.sub(r"©.*?Autodesk.*?\n", "", text)
    return text.strip()


def extract_text_from_pdf(pdf_path: Path) -> list[dict]:
    """Извлекает текст из PDF постранично."""
    doc = fitz.open(str(pdf_path))
    pages = []
    for page_num in range(len(doc)):
        text = clean_text(doc[page_num].get_text("text"))
        if len(text.strip()) > 50:  # пропускаем пустые страницы
            pages.append({
                "page": page_num + 1,
                "text": text,
                "source": pdf_path.name,
            })
    doc.close()
    return pages


def parse_all_pdfs() -> list[dict]:
    """Парсит все PDF из data/pdf (на диске E) в output/parsed_docs.txt."""
    pdf_files = sorted(PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"⚠️ Нет PDF файлов в {PDF_DIR}!")
        print("   Положи PDF справки PowerMill в эту папку (диск E).")
        return []

    print(f"📄 Найдено {len(pdf_files)} PDF файлов")

    all_pages = []
    for pdf_path in tqdm(pdf_files, desc="Парсинг PDF"):
        try:
            pages = extract_text_from_pdf(pdf_path)
            all_pages.extend(pages)
            print(f"  ✅ {pdf_path.name}: {len(pages)} страниц")
        except Exception as e:
            print(f"  ❌ {pdf_path.name}: {e}")

    output_file = OUTPUT_DIR / "parsed_docs.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        for page in all_pages:
            f.write(f"\n{'=' * 60}\n")
            f.write(f"Источник: {page['source']} | Страница: {page['page']}\n")
            f.write(f"{'=' * 60}\n")
            f.write(page["text"] + "\n")

    print(f"\n✅ Итого: {len(all_pages)} страниц из {len(pdf_files)} PDF")
    print(f"💾 Сохранено в {output_file}")
    return all_pages


if __name__ == "__main__":
    parse_all_pdfs()
