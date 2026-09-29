"""
Настоящие макросы с диска как источник для генерации PML.

Зачем
-----
Лучший «учебник» по PML — рабочие макросы: в них видно настоящий синтаксис
(`CREATE BOUNDARY ;`, `EDIT TOOLPATH "1" ; REORDER`, `FOREACH ... IN FOLDER("…")`).
Autodesk кладёт примеры макросов в установку PowerMill, а технолог — в
`data\\macros`. Этот модуль находит `.mac`-файлы и превращает их в страницы
базы знаний (kind="macro"), чтобы:

* `/macro` видел реальные примеры в контексте;
* поиск по справке (пункт 2) находил макросы («найди макрос, который делает
  припуск»);
* словарь PML (src/pml_vocab.py) пополнялся настоящими именами и параметрами.

Приоритет макросов в поиске высокий (0.15) — это рабочий код, а не таблица
параметров.
"""
from __future__ import annotations

import re
from pathlib import Path

from config import MACRO_DIR

MACRO_EXTS = (".mac", ".pml", ".mac.txt")
MAX_MACROS = 400                 # защита от гигантских папок
MAX_MACRO_CHARS = 12_000         # в поиск кладём только читаемую часть

# Папки установки PowerMill, где обычно лежат примеры макросов.
# Используется скриптом scripts/find_macros.py (он подсказывает пользователю,
# куда смотреть; сканировать весь диск не нужно).
INSTALL_HINTS = (
    r"E:\powermill 2026\PowerMill 2026\lib\macros",
    r"E:\powermill 2026\PowerMill 2026\lib\macro",
    r"E:\powermill 2026\PowerMill 2026\macros",
    r"C:\Program Files\Autodesk\PowerMill 2026\lib\macros",
    r"C:\ProgramData\Autodesk\PowerMill\2026\macros",
    r"C:\ProgramData\Autodesk\PowerMill\macros",
)

# Каталоги, которые бессмысленно обходить целиком
SKIP_DIRS = {"windows", "$recycle.bin", "system volume information", "node_modules",
             "__pycache__", ".git", "appdata"}

_TITLE_RE = re.compile(r"(?m)^\s*//\s*(.+)$")


def _title_for(path: Path, text: str) -> str:
    """Человеческое название макроса: первая строка комментария или имя файла."""
    match = _TITLE_RE.search(text)
    if match:
        title = match.group(1).strip()
        # Пропускаем шапки вида «=====» и бессмысленные строки
        if 3 < len(title) < 90 and not set(title) <= set("=-*# "):
            return title
    return path.stem


def describe(path: Path) -> dict | None:
    """Один .mac-файл -> запись базы знаний (или None, если файл пустой)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return None

    rel = path.name
    try:
        rel = path.relative_to(MACRO_DIR).as_posix()
    except ValueError:
        pass

    title = _title_for(path, text)
    body = (
        f"// Макрос PML: {title}\n"
        f"// Файл: {path}\n"
        f"// Это рабочий макрос — настоящий синтаксис PML, можно опираться на него.\n\n"
        + text[:MAX_MACRO_CHARS]
    )
    return {
        "source": f"Макросы/{rel}",
        "root": "macros",
        "path": rel,
        "lang": "mac",
        "kind": "macro",
        "title": f"Макрос: {title}",
        "breadcrumb": f"Макросы (примеры с диска) > {title}",
        "section": "Макросы (примеры с диска)",
        "order": 1,
        "text_chars": len(body),
        "extracted_from": "macro",
        "priority": 0.15,
        "redirect_to": "",
        "contextid": "",
        "topicid": "",
        "topic_type": "macro",
        "text": body,
    }


def collect(root: Path | None = None, limit: int = MAX_MACROS) -> list[dict]:
    """Все макросы из папки в виде записей базы знаний."""
    root = Path(root or MACRO_DIR)
    if not root.exists():
        return []

    found: list[Path] = []
    for ext in MACRO_EXTS:
        found += sorted(root.rglob(f"*{ext}"))
    # .mac.txt имеет приоритет над .mac только если это разные файлы
    unique: list[Path] = []
    seen: set[str] = set()
    for path in found:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)

    pages: list[dict] = []
    for path in unique[:limit]:
        page = describe(path)
        if page:
            pages.append(page)
    return pages


def find_on_disk(roots: list[str] | None = None, limit: int = MAX_MACROS) -> list[Path]:
    """Ищет .mac в подсказанных папках (без полного сканирования диска)."""
    candidates: list[Path] = [Path(r) for r in (roots or INSTALL_HINTS)]
    candidates.append(MACRO_DIR)

    found: list[Path] = []
    seen: set[str] = set()
    for root in candidates:
        if not root.exists() or not root.is_dir():
            continue
        if any(part.lower() in SKIP_DIRS for part in root.parts):
            continue
        try:
            for path in root.rglob("*"):
                if len(found) >= limit:
                    return found
                if not path.is_file():
                    continue
                if any(part.lower() in SKIP_DIRS for part in path.parts):
                    continue
                if path.suffix.lower() in (".mac", ".pml"):
                    key = str(path).lower()
                    if key not in seen:
                        seen.add(key)
                        found.append(path)
        except OSError:
            continue
    return found


def main() -> int:
    """Собирает макросы из data\\macros в output/macro_pages.jsonl (для отладки)."""
    import json

    from config import OUTPUT_DIR

    pages = collect()
    out = OUTPUT_DIR / "macro_pages.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for page in pages:
            handle.write(json.dumps(page, ensure_ascii=False) + "\n")

    print(f"Макросов найдено: {len(pages)} -> {out}")
    for page in pages[:20]:
        print(f"  {page['breadcrumb']}  ({page['text_chars']} симв.)")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
