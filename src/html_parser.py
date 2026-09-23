"""
Парсер локальной HTML-справки PowerMill.

Обходит HELP_DIR (оффлайн-справка ProgramData) + PML PARREF,
вытаскивает чистый текст и сохраняет в output/parsed_html.txt
в том же формате, что и src.pdf_parser (для общего чанкера).
"""
import re
from pathlib import Path

from tqdm import tqdm

from config import HELP_DIR, HELP_DIR_DEFAULT_EXTRAS, HELP_DIR_EXTRA, OUTPUT_DIR

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


def help_roots() -> list[Path]:
    """Все корни справки: HELP_DIR + доп. из env + PML-справочник установки."""
    roots: list[Path] = [HELP_DIR]
    roots.extend(HELP_DIR_EXTRA)
    roots.extend(HELP_DIR_DEFAULT_EXTRAS)
    # дедуп, только существующие папки
    seen: set[Path] = set()
    out: list[Path] = []
    for r in roots:
        try:
            r = r.resolve()
        except OSError:
            pass
        if r in seen:
            continue
        seen.add(r)
        if r.exists() and r.is_dir():
            out.append(r)
        else:
            print(f"ℹ Справка не найдена, пропускаю: {r}")
    return out


def parse_all_help() -> list[dict]:
    """Парсит всю локальную HTML-справку -> output/parsed_html.txt."""
    roots = help_roots()
    if not roots:
        print("⚠ Не найдено ни одной папки справки.")
        print("   Задай: set POWERMILL_HELP_DIR=C:\\...\\Help")
        print("   Найти: scripts\\find_help.bat")
        return []

    all_files: list[tuple[Path, Path]] = []  # (root, file)
    for root in roots:
        files = list(iter_help_files(root))
        print(f"📘 {root}: {len(files)} HTML")
        for f in files:
            all_files.append((root, f))

    if not all_files:
        print("⚠ HTML-файлы не найдены.")
        return []

    print(f"📘 Всего: {len(all_files)} HTML-файлов справки")

    pages: list[dict] = []
    for root, path in tqdm(all_files, desc="Парсинг HTML"):
        try:
            title, text = html_to_text(path)
            if len(text) < 50:
                continue
            rel = str(path.relative_to(root))
            # чтобы не путать одноимённые файлы из разных корней
            source = f"{root.name}/{rel}"
            pages.append({"title": title, "text": text, "source": source})
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
