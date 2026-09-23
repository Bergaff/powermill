"""
Парсер локальной HTML-справки PowerMill.

Обходит POWERMILL_HELP_DIR (по умолчанию папка lib/locale/C у PowerMill 2026),
вытаскивает чистый текст и сохраняет в output/parsed_html.txt
в том же формате, что и src.pdf_parser (для общего чанкера).
"""
import re
from pathlib import Path

from tqdm import tqdm

from config import HELP_DIR, OUTPUT_DIR

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

OUTPUT_FILE = OUTPUT_DIR / "parsed_html.txt"

# Служебные/ненужные для знаний базы пути
SKIP_PARTS = {"bin", "res", "images", "image", "css", "js", "scripts"}


def html_to_text(path: Path) -> tuple[str, str]:
    """HTML-файл -> (заголовок, чистый текст)."""
    raw = path.read_text(encoding="utf-8", errors="ignore")

    if BeautifulSoup is not None:
        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
            tag.decompose()
        title = (soup.title.string if soup.title else "") or path.stem
        text = soup.get_text("\n")
    else:
        # Фолбэк без BeautifulSoup: срезаем скрипты/стили и теги
        raw = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
        m = re.search(r"(?is)<title>(.*?)</title>", raw)
        title = m.group(1).strip() if m else path.stem
        text = re.sub(r"(?s)<[^>]+>", " ", raw)
        from html import unescape
        text = unescape(text)

    # Очистка: пробелы, пустые строки, типичный мусор справки
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [ln.strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    return title.strip(), text.strip()


def iter_help_files(root: Path):
    """Все .html/.htm под корнем, кроме служебных папок."""
    patterns = ("*.html", "*.htm")
    seen = set()
    for pattern in patterns:
        for path in sorted(root.rglob(pattern)):
            parts_lower = {p.lower() for p in path.relative_to(root).parts[:-1]}
            if parts_lower & SKIP_PARTS:
                continue
            if path in seen:
                continue
            seen.add(path)
            yield path


def parse_all_help() -> list[dict]:
    """Парсит всю локальную HTML-справку -> output/parsed_html.txt."""
    root = Path(HELP_DIR)
    if not root.exists():
        print(f"⚠️ Папка справки не найдена: {root}")
        print("   Задай свой путь: set POWERMILL_HELP_DIR=E:\\...\\help")
        print("   (найди folder с parameters.html / index.html)")
        return []

    files = list(iter_help_files(root))
    if not files:
        print(f"⚠️ HTML-файлы не найдены в {root}")
        return []

    print(f"📘 Найдено {len(files)} HTML-файлов справки в {root}")

    pages: list[dict] = []
    for path in tqdm(files, desc="Парсинг HTML"):
        try:
            title, text = html_to_text(path)
            if len(text) < 50:
                continue
            rel = str(path.relative_to(root))
            pages.append({"title": title, "text": text, "source": rel})
        except Exception as e:
            print(f"  ❌ {path.name}: {e}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for page in pages:
            f.write(f"\n{'=' * 60}\n")
            f.write(f"Источник: {page['source']} | Заголовок: {page['title']}\n")
            f.write(f"{'=' * 60}\n")
            f.write(page["text"] + "\n")

    print(f"✅ Извлечено {len(pages)} страниц справки -> {OUTPUT_FILE}")
    return pages


if __name__ == "__main__":
    parse_all_help()
