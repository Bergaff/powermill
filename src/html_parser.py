"""
Парсер локальной HTML-справки PowerMill.

Обходит HELP_DIR (оффлайн-справка ProgramData) + PML PARREF,
вытаскивает чистый текст и сохраняет в output/parsed_html.txt
в том же формате, что и src.pdf_parser (для общего чанкера).
"""
import re
from pathlib import Path
from html import unescape

from tqdm import tqdm

from config import HELP_DIR, HELP_DIR_DEFAULT_EXTRAS, HELP_DIR_EXTRA, OUTPUT_DIR

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

OUTPUT_FILE = OUTPUT_DIR / "parsed_html.txt"

# Служебные/ненужные для знаний базы пути
SKIP_PARTS = {"bin", "res", "images", "image", "css", "js", "scripts"}

# Порог: короче — служебная заглушка/очень короткая context-подсказка.
# (15 ловит короткие, но осмысленные contexthelp-термины вроде "3D выборка")
MIN_TEXT_LEN = 15


def decode_html(raw: bytes) -> str:
    """Кодировка HTML: meta charset → BOM → utf-8 → cp1251 (рус. справка)."""
    if not raw:
        return ""
    m = re.search(br"charset\s*=\s*[\"']?([\w\-]+)", raw[:4096], re.I)
    if m:
        cs = m.group(1).decode("ascii", "ignore").lower()
        try:
            return raw.decode(cs, errors="replace")
        except LookupError:
            pass
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig", errors="replace")
    for enc in ("utf-8", "cp1251", "windows-1251"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    # последний шанс: cp1251 не бросает ошибок на любых байтах
    return raw.decode("cp1251", errors="replace")


def html_to_text(path: Path) -> tuple[str, str]:
    """HTML-файл -> (заголовок, чистый текст)."""
    raw = path.read_bytes()
    data = decode_html(raw)

    if BeautifulSoup is not None:
        soup = BeautifulSoup(data, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
            tag.decompose()
        title = (soup.title.string if soup.title else "") or path.stem
        text = soup.get_text("\n")
    else:
        data = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", data)
        m = re.search(r"(?is)<title>(.*?)</title>", data)
        title = m.group(1).strip() if m else path.stem
        text = unescape(re.sub(r"(?s)<[^>]+>", " ", data))

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

    all_files: list[tuple[Path, Path]] = []
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
    short = 0
    short_samples: list[str] = []
    errors = 0

    # статистика: корень -> подпапка -> (найдено, извлечено, сумма символов)
    stats: dict[str, dict[str, list[int]]] = {}

    for root, path in tqdm(all_files, desc="Парсинг HTML"):
        try:
            title, text = html_to_text(path)
            rel = path.relative_to(root)
            # группировка: первые 2 компонента пути (Help\l.rus\contexthelp\...)
            if len(rel.parts) >= 3:
                top = "\\".join(rel.parts[:3])
            elif len(rel.parts) == 2:
                top = "\\".join(rel.parts)
            else:
                top = rel.parts[0]
            st = stats.setdefault(str(root.name), {})
            cell = st.setdefault(top, [0, 0, 0])
            cell[0] += 1

            if len(text) < MIN_TEXT_LEN:
                short += 1
                if len(short_samples) < 8:
                    snip = text[:70].replace("\n", " ")
                    short_samples.append(f"   {len(text):>4} симв.  {rel}  | {snip}")
                continue

            cell[1] += 1
            cell[2] += len(text)
            source = f"{root.name}/{rel}"
            pages.append({"title": title, "text": text, "source": source})
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  ❌ {path.name}: {e}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for page in pages:
            f.write(f"\n{'=' * 60}\n")
            f.write(f"Источник: {page['source']} | Заголовок: {page['title']}\n")
            f.write(f"{'=' * 60}\n")
            f.write(page["text"] + "\n")

    print(f"✅ Извлечено {len(pages)} страниц из {len(all_files)} HTML -> {OUTPUT_FILE}")

    print("\n📊 По подпапкам (найдено / извлечено / сумма символов):")
    for root_name, st in stats.items():
        print(f"  [{root_name}]")
        for sub, (n_found, n_ok, chars) in sorted(
            st.items(), key=lambda kv: -kv[1][2]
        ):
            print(f"    {sub:<28} {n_found:>5} / {n_ok:>5}  {chars:>9} симв.")

    if pages:
        longest = sorted(pages, key=lambda p: -len(p["text"]))[:5]
        print("\n📏 Самые длинные статьи (значит, полные тексты есть):")
        for p in longest:
            src = p["source"][:70]
            print(f"    {len(p['text']):>6} симв.  {src}")

    if short:
        print(f"\n✂ Короче {MIN_TEXT_LEN} симв. (заглушки/пустые): {short}")
        for s in short_samples:
            print(s)
    if errors:
        print(f"❌ Ошибок чтения: {errors}")
    return pages


if __name__ == "__main__":
    parse_all_help()
