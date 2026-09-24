"""
Парсер локальной HTML-справки PowerMill (оффлайн Help + PML PARREF).

ГЛАВНОЕ ПРО ОФФЛАЙН-СПРАВКУ AUTODESK
------------------------------------
Внутри `C:\\ProgramData\\Autodesk\\PowerMill\\2026\\Help\\l.rus\\`:

    files\\*.htm            1350 шт., ~850 байт каждый — ПУСТЫШКИ (только скрипты).
                           Текста внутри нет! Именно поэтому прошлый парсер
                           нашёл «0 страниц».
    wrapped-files\\*.htm.js 1350 шт., 0.5-55 КБ — ЗДЕСЬ НАСТОЯЩИЙ ТЕКСТ страниц
                           (HTML, зашитый в JS-строку).
    scripts\\toc-treedata.js  дерево оглавления со всеми заголовками.
    contexthelp\\*.htm       1255 коротких подсказок-терминов.

Что делает этот парсер:
  1. находит языковую папку (l.rus по умолчанию) — без дублей RU+EN;
  2. берёт `files\\<имя>.htm`, а если там пустышка — читает
     `wrapped-files\\<имя>.js` и разворачивает обёртку (src.help_extract);
  3. подтягивает заголовок и иерархию из оглавления (src.toc_parser);
  4. пишет три файла в output\\:
       help_pages.jsonl  — по странице на строку (заголовок, раздел, текст);
       parsed_html.txt   — то же, человекочитаемо (совместимость со старым кодом);
       help_report.txt   — отчёт: сколько страниц, где, что нашлось.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

try:  # tqdm — только для прогресс-бара; без него разбор всё равно работает
    from tqdm import tqdm
except ImportError:  # pragma: no cover
    def tqdm(iterable, **kwargs):
        total = kwargs.get("total") or (len(iterable) if hasattr(iterable, "__len__") else "?")
        print(f"   ... разбираю {total} файлов (без прогресс-бара)")
        return iterable

from config import (
    HELP_DIR,
    HELP_DIR_DEFAULT_EXTRAS,
    HELP_DIR_EXTRA,
    HELP_FILE_LIMIT,
    HELP_FILES_DIR,
    HELP_LANG,
    HELP_LANG_PRIORITY,
    HELP_WRAPPED_DIR,
    OUTPUT_DIR,
)
from src.help_extract import (
    extract_page_text,
    is_generic_title,
    looks_like_help_root,
    load_page,
)
from src.toc_parser import load_toc, save_toc

OUTPUT_FILE = OUTPUT_DIR / "parsed_html.txt"      # совместимость
PAGES_FILE = OUTPUT_DIR / "help_pages.jsonl"      # основной формат
REPORT_FILE = OUTPUT_DIR / "help_report.txt"

SKIP_PARTS = {"bin", "res", "images", "image", "css", "js", "scripts", "wrapped-files"}

# Нестандартный корень: папка установки PowerMill (lib\locale\C) со справочником
# PML — PARREF (параметры), PARSUM (сводка), DOC/HELP.
NONSTD_DIRS = ("parref", "parsum", "doc", "help", "commands", "parameters")
# Расширения текстовых файлов справки в таких папках
NONSTD_EXTS = (".htm", ".html", ".txt", ".xml")
MAX_TEXT_FILE_MB = 5.0

# Порог «страница не пустая». 15 ловит короткие contexthelp-термины.
MIN_TEXT_LEN = 15

# Кандидаты имён «обёрнутых» файлов для страницы files\\GUID-1.htm
WRAPPED_SUFFIXES = ("", ".js")


# --------------------------------------------------------------------------
# Поиск корней справки
# --------------------------------------------------------------------------
LANG_DIR_RE = re.compile(r"^l\.[a-z]{2,3}$", re.I)


def help_roots() -> list[Path]:
    """Корни справки: HELP_DIR + extras, существующие."""
    roots: list[Path] = [HELP_DIR, *HELP_DIR_EXTRA, *HELP_DIR_DEFAULT_EXTRAS]
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


def is_nonstd_root(root: Path) -> bool:
    """Похоже ли, что это папка установки PowerMill со справочником PML."""
    try:
        names = {p.name.lower() for p in root.iterdir() if p.is_dir()}
    except OSError:
        return False
    return bool(names & set(NONSTD_DIRS))


def pick_lang_dir(root: Path, lang: str) -> Path | None:
    """Выбирает языковую папку внутри Help: l.rus / l.enu / ... (без дублей)."""
    if looks_like_help_root(root):
        return root  # это уже языковая папка (внутри files/ или scripts/)
    try:
        subdirs = [p for p in root.iterdir() if p.is_dir() and LANG_DIR_RE.match(p.name)]
    except OSError:
        return None
    if not subdirs:
        # справочник PML установки PowerMill (PARREF/PARSUM/DOC/HELP)
        return root if is_nonstd_root(root) else None

    by_lang = {p.name.split(".", 1)[1].lower(): p for p in subdirs}
    if lang and lang != "auto":
        return by_lang.get(lang)
    for code in HELP_LANG_PRIORITY:
        if code in by_lang:
            return by_lang[code]
    return sorted(subdirs)[0]


def iter_page_files(root: Path):
    """Файлы-страницы справки: все .htm/.html, кроме служебных папок.

    Обычно это `files\\*.htm` (1350 тем) + `contexthelp\\*.htm`
    (1255 терминов). Для папки установки PowerMill (PARREF/PARSUM/DOC/HELP)
    дополнительно читаются .txt/.xml.
    """
    candidates = sorted(root.rglob("*.htm")) + sorted(root.rglob("*.html"))
    if is_nonstd_root(root):
        for ext in (".txt", ".xml"):
            candidates += sorted(root.rglob(f"*{ext}"))
    for p in candidates:
        parts = {seg.lower() for seg in p.relative_to(root).parts[:-1]}
        if parts & SKIP_PARTS:
            continue
        if p.suffix.lower() in (".txt", ".xml"):
            try:
                if p.stat().st_size > MAX_TEXT_FILE_MB * 1e6:
                    print(f"ℹ Пропускаю большой файл: {p.name}")
                    continue
            except OSError:
                continue
        yield p


def wrapped_candidates(root: Path, page: Path) -> list[Path]:
    """Возможные «обёрнутые» файлы для страницы (wrapped-files\\<имя>.js и т.п.)."""
    names = [page.name, page.stem + ".htm", page.stem + ".html"]
    out: list[Path] = []
    for wrapped_dir in (root / HELP_WRAPPED_DIR, page.parent.parent / HELP_WRAPPED_DIR,
                        page.parent / HELP_WRAPPED_DIR):
        if not wrapped_dir.is_dir():
            continue
        for name in names:
            for suffix in WRAPPED_SUFFIXES:
                cand = wrapped_dir / (name + suffix)
                if cand.is_file():
                    out.append(cand)
    return out


def page_kind(root: Path, page: Path) -> str:
    """Тип страницы по расположению: contexthelp / pml / page."""
    rel = str(page.relative_to(root)).replace("\\", "/").lower()
    if "contexthelp" in rel or rel.startswith("ctx"):
        return "contexthelp"
    if "parref" in rel or "parsum" in rel or "cmdref" in rel:
        return "pml"
    return "page"


def crumb_title(toc_entry: dict | None, title: str) -> str:
    if toc_entry and toc_entry.get("breadcrumb"):
        return " > ".join([*toc_entry["breadcrumb"], title or toc_entry["title"]])
    return title


def _read_text(path: Path) -> tuple[str, str]:
    """Файл -> (заголовок, текст). Ошибок не бросает."""
    try:
        raw = path.read_bytes()
    except OSError:
        return "", ""
    if path.suffix.lower() in (".txt", ".xml"):
        from src.help_extract import decode_html, html_to_structured_text

        text = decode_html(raw)
        if path.suffix.lower() == ".xml" and "<" in text[:200]:
            text = html_to_structured_text(text)
        return path.stem, text.strip()
    return extract_page_text(raw, path)


def wrapped_html(root: Path, page: Path) -> dict:
    """Читает wrapped-файл страницы (там лежит настоящий HTML и его метаданные)."""
    for cand in wrapped_candidates(root, page):
        info = load_page(cand)
        if len(info["text"]) >= MIN_TEXT_LEN:
            return info
    return {}


def parse_page(root: Path, page: Path, toc_map: dict[str, dict]) -> dict | None:
    """Одна страница справки -> словарь. None, если текста нет."""
    stub = load_page(page)                      # .htm: заглушка, но с метаданными
    title, text = stub["title"], stub["text"]
    meta = dict(stub["meta"])
    redirect_to = stub["redirect_to"] or ""
    source_used = "htm"

    if len(text) < MIN_TEXT_LEN:
        wrapped = wrapped_html(root, page)      # настоящий текст страницы
        if wrapped:
            title = wrapped["title"] or title
            text = wrapped["text"]
            source_used = "wrapped"
            for key, value in wrapped["meta"].items():
                meta.setdefault(key, value)
            redirect_to = redirect_to or wrapped["redirect_to"]

    topic_type = (meta.get("topic-type") or "").lower()

    # Страницы-редиректы (contexthelp): полезного текста нет, но есть
    # человеческий заголовок термина и ссылка на настоящую страницу —
    # такие записи пригодятся для поиска по терминам.
    if len(text.strip()) < MIN_TEXT_LEN:
        if topic_type == "redirect" or redirect_to:
            rel_short = page.relative_to(root).as_posix()
            return {
                "source": f"{root.name}/{rel_short}",
                "root": root.name,
                "path": rel_short,
                "lang": root.name,
                "kind": "redirect",
                "title": title or page.stem,
                "breadcrumb": title or page.stem,
                "section": "",
                "order": 10_000,
                "text_chars": 0,
                "extracted_from": "redirect",
                "redirect_to": redirect_to,
                "contextid": meta.get("contextid", ""),
                "topicid": meta.get("topicid", ""),
                "topic_type": topic_type,
                "text": "",
            }
        return None

    rel = page.relative_to(root).as_posix()
    toc_entry = toc_map.get(rel.lower()) or toc_map.get(
        (HELP_FILES_DIR + "/" + page.name).lower()
    )
    # Заголовок: осмысленный <h1>/<title> из страницы важнее, а оглавление
    # подставляет заголовок там, где в файле его нет (обычный случай).
    toc_title = (toc_entry or {}).get("title", "")
    if toc_title and is_generic_title(title, page):
        title = toc_title

    return {
        "source": f"{root.name}/{rel}",
        "root": root.name,
        "path": rel,
        "lang": root.name,
        "kind": page_kind(root, page),
        "title": title,
        "breadcrumb": crumb_title(toc_entry, title),
        "section": " > ".join(toc_entry["breadcrumb"]) if toc_entry else "",
        "order": toc_entry["order"] if toc_entry else 10_000,
        "text_chars": len(text),
        "extracted_from": source_used,
        "redirect_to": redirect_to,
        "contextid": meta.get("contextid", ""),
        "topicid": meta.get("topicid", ""),
        "topic_type": topic_type or ("concept" if text else ""),
        "text": text,
    }


# --------------------------------------------------------------------------
# Основной проход
# --------------------------------------------------------------------------
def parse_all_help(limit: int | None = None, lang: str | None = None,
                   roots: list[Path] | None = None) -> list[dict]:
    """Парсит справку -> output/help_pages.jsonl (+ parsed_html.txt, help_report)."""
    roots = roots if roots is not None else help_roots()
    limit = HELP_FILE_LIMIT if limit is None else limit
    lang = (lang or HELP_LANG).lower()

    if not roots:
        print("⚠ Не найдено ни одной папки справки.")
        print("   Задай: set POWERMILL_HELP_DIR=C:\\...\\Help")
        print("   Найти: scripts\\find_help.bat")
        return []

    print("📘 Справка: ищу языковые папки...")
    lang_roots: list[Path] = []
    for root in roots:
        chosen = pick_lang_dir(root, lang)
        if chosen is None:
            print(f"   ⚠ {root}: нет ни языковых папок (l.rus/l.enu), ни files/")
            continue
        if chosen != root:
            print(f"   ✓ {root} -> язык '{chosen.name}'")
        else:
            print(f"   ✓ {root} (корень справки)")
        lang_roots.append(chosen)

    if not lang_roots:
        print("\n⚠ Не нашёл папку с языком справки.")
        print("   Запусти: scripts\\find_help.bat и пришли вывод — я подскажу путь.")
        return []

    toc_map, toc_nodes = load_toc(lang_roots)
    if toc_map:
        json_path, txt_path = save_toc(toc_map, toc_nodes, OUTPUT_DIR)
        print(f"🗂 Оглавление: {len(toc_nodes)} узлов -> {txt_path.name}, {json_path.name}")

    all_files: list[tuple[Path, Path]] = []
    for root in lang_roots:
        files = list(iter_page_files(root))
        print(f"📘 {root.name}: {len(files)} файлов-страниц")
        all_files.extend((root, f) for f in files)

    if not all_files:
        print("⚠ HTML-файлы не найдены.")
        return []

    if limit and limit > 0:
        all_files = all_files[:limit]
        print(f"⏱ Ограничение: парсим только {len(all_files)} файлов (для проверки)")

    print(f"📘 Всего к разбору: {len(all_files)} страниц")

    pages: list[dict] = []
    redirects: list[dict] = []
    stats: dict[str, dict[str, list[int]]] = {}
    seen_hashes: dict[str, str] = {}
    duplicates = 0
    empty = 0
    errors = 0
    from_wrapped = 0
    empty_samples: list[str] = []

    for root, path in tqdm(all_files, desc="Парсинг HTML"):
        try:
            page = parse_page(root, path, toc_map)
        except Exception as e:  # noqa: BLE001 — одна битая страница не должна ронять всё
            errors += 1
            if errors <= 5:
                print(f"  ❌ {path.name}: {e}")
            continue

        rel = path.relative_to(root).as_posix()
        key = f"{root.name}:{'/'.join(rel.split('/')[:2])}"
        cell = stats.setdefault(key, [0, 0, 0])
        cell[0] += 1

        if page is None:
            empty += 1
            if len(empty_samples) < 6:
                empty_samples.append(f"   {rel}")
            continue

        if not page.get("text"):
            # страница-редирект: текста нет, но есть заголовок термина
            redirects.append(page)
            continue

        digest = hashlib.md5(page["text"].encode("utf-8")).hexdigest()
        if digest in seen_hashes:
            duplicates += 1
            continue
        seen_hashes[digest] = rel

        if page["extracted_from"].startswith("wrapped"):
            from_wrapped += 1

        cell[1] += 1
        cell[2] += page["text_chars"]
        pages.append(page)

    # Разрешаем редиректы: заголовок термина уходит в aliases целевой страницы.
    # Так «Иерархия 2D-элементов» ищется по настоящей статье, а не по пустышке.
    by_rel = {p["path"].lower(): p for p in pages}
    by_name = {Path(p["path"]).name.lower(): p for p in pages}
    resolved = 0
    leftover_redirects: list[dict] = []
    for red in redirects:
        target = (red.get("redirect_to") or "").replace("\\", "/").lower()
        target_page = None
        if target:
            target_page = by_rel.get(target) or by_name.get(Path(target).name)
            if target_page is None and not target.startswith("files/"):
                target_page = by_rel.get("files/" + target) or by_rel.get(target)
        if target_page is not None:
            aliases = target_page.setdefault("aliases", [])
            term = red.get("title", "")
            if term and term not in aliases:
                aliases.append(term)
            if red.get("contextid"):
                target_page.setdefault("contextids", [])
                if red["contextid"] not in target_page["contextids"]:
                    target_page["contextids"].append(red["contextid"])
            resolved += 1
        else:
            leftover_redirects.append(red)

    # Второй шанс: привязка по contextid. В files\*.htm есть
    # <meta name="contextid" content="TOOLDIALOG"> — у термина-редиректа он часто тот же.
    by_context: dict[str, dict] = {}
    for page in pages:
        for cid in page.get("contextids") or []:
            by_context.setdefault(cid.upper(), page)
        if page.get("contextid"):
            by_context.setdefault(page["contextid"].upper(), page)

    still_left: list[dict] = []
    for red in leftover_redirects:
        cid = (red.get("contextid") or "").upper()
        target_page = by_context.get(cid) if cid else None
        if target_page is not None:
            aliases = target_page.setdefault("aliases", [])
            term = red.get("title", "")
            if term and term not in aliases:
                aliases.append(term)
            resolved += 1
        else:
            still_left.append(red)
    leftover_redirects = still_left

    # Оставшиеся термины держим как короткие записи-подсказки: по названию
    # термина всё равно можно найти нужный раздел справки.
    for red in leftover_redirects:
        term = red.get("title", "")
        red["text"] = (f"Термин справки PowerMill: «{term}». "
                       f"Смотрите соответствующий раздел документации.")
        red["text_chars"] = len(red["text"])
        red["extracted_from"] = "redirect-only"

    pages.extend(leftover_redirects)

    pages.sort(key=lambda p: (p["order"], p["source"]))

    PAGES_FILE.write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in pages), encoding="utf-8"
    )

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for page in pages:
            f.write(f"\n{'=' * 60}\n")
            f.write(f"Источник: {page['source']} | Заголовок: {page['title']}\n")
            if page["section"]:
                f.write(f"Раздел: {page['section']}\n")
            f.write(f"{'=' * 60}\n")
            f.write(page["text"] + "\n")

    total_chars = sum(p["text_chars"] for p in pages)
    print(f"\n✅ Извлечено {len(pages)} страниц "
          f"({total_chars / 1_000_000:.1f} млн символов)")
    print(f"   из них через wrapped-files: {from_wrapped}")
    print(f"   терминов-редиректов привязано к статьям: {resolved}")
    print(f"   терминов без статьи (остались как подсказки): {len(leftover_redirects)}")
    print(f"   пустых/служебных: {empty}, дублей: {duplicates}, ошибок: {errors}")
    print(f"💾 {PAGES_FILE}")
    print(f"💾 {OUTPUT_FILE}")

    print("\n📊 По папкам (найдено / извлечено / символов):")
    for key, (n_found, n_ok, chars) in sorted(stats.items(), key=lambda kv: -kv[1][2]):
        print(f"    {key:<40} {n_found:>5} / {n_ok:>5}  {chars:>9}")

    if pages:
        print("\n📏 Самые длинные статьи:")
        for p in sorted(pages, key=lambda p: -p["text_chars"])[:5]:
            print(f"    {p['text_chars']:>6} симв.  {p['breadcrumb'][:80]}")

        print("\n🗂 Крупные разделы справки:")
        from collections import Counter

        top = Counter(p["section"].split(" > ")[0] for p in pages if p["section"])
        for name, cnt in top.most_common(12):
            print(f"    {cnt:>4} стр.  {name}")

    if empty_samples:
        print("\n✂ Примеры страниц без текста:")
        for s in empty_samples:
            print(s)

    REPORT_FILE.write_text(
        _report_text(pages, stats, empty, duplicates, errors, from_wrapped,
                     toc_nodes, empty_samples, lang_roots),
        encoding="utf-8",
    )
    print(f"📝 Отчёт: {REPORT_FILE} (можно прислать целиком в чат)")
    return pages


def _report_text(pages, stats, empty, duplicates, errors, from_wrapped,
                 toc_nodes, empty_samples, lang_roots) -> str:
    from collections import Counter

    lines = [
        "=" * 70,
        "ОТЧЁТ: разбор оффлайн-справки PowerMill",
        "=" * 70,
        f"Корни справки: {', '.join(str(r) for r in lang_roots)}",
        f"Страниц извлечено: {len(pages)}",
        f"  - через wrapped-files (JS-обёртка): {from_wrapped}",
        f"  - напрямую из HTML: {len(pages) - from_wrapped}",
        f"Символов всего: {sum(p['text_chars'] for p in pages):,}",
        f"Пустых/служебных: {empty} | дублей: {duplicates} | ошибок: {errors}",
        f"Узлов оглавления: {len(toc_nodes)}",
        "",
        "ПО ПАПКАМ: найдено / извлечено / символов",
    ]
    for key, (n_found, n_ok, chars) in sorted(stats.items(), key=lambda kv: -kv[1][2]):
        lines.append(f"  {key:<45} {n_found:>5} / {n_ok:>5}  {chars:>10}")
    lines.append("")
    lines.append("ТИПЫ СТРАНИЦ:")
    for kind, cnt in Counter(p["kind"] for p in pages).most_common():
        lines.append(f"  {kind:<15} {cnt:>5}")
    lines.append("")
    lines.append("КРУПНЫЕ РАЗДЕЛЫ (верхний уровень оглавления):")
    for name, cnt in Counter(
        p["section"].split(" > ")[0] for p in pages if p["section"]
    ).most_common(40):
        lines.append(f"  {cnt:>5} стр.  {name}")
    lines.append("")
    lines.append("САМЫЕ ДЛИННЫЕ СТАТЬИ:")
    for p in sorted(pages, key=lambda p: -p["text_chars"])[:25]:
        lines.append(f"  {p['text_chars']:>7}  {p['breadcrumb'][:100]}")
    if empty_samples:
        lines.append("")
        lines.append("ПРИМЕРЫ ПУСТЫХ СТРАНИЦ:")
        lines.extend(empty_samples)
    lines.append("")
    lines.append("ПЕРВЫЕ 60 УЗЛОВ ОГЛАВЛЕНИЯ:")
    from src.toc_parser import toc_as_tree_text

    lines.append(toc_as_tree_text(toc_nodes, max_nodes=60))
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Парсер оффлайн-справки PowerMill")
    ap.add_argument("--limit", type=int, default=None,
                    help="разобрать только N первых страниц (проверка)")
    ap.add_argument("--lang", default=None, help="язык справки: rus / enu / auto")
    ap.add_argument("--root", action="append", default=None,
                    help="свой корень справки (можно несколько раз)")
    args = ap.parse_args()

    # весь вывод дублируем в output\logs\parse_help.log — если окно закроется,
    # батник покажет хвост лога, а файл можно прислать в чат
    from src.applog import log_error_to_file, start_log

    log_file = start_log("parse_help")
    print(f"Лог этого запуска: {log_file}\n")
    try:
        roots = [Path(p) for p in args.root] if args.root else None
        pages = parse_all_help(limit=args.limit, lang=args.lang, roots=roots)
        if not pages:
            print("\n(!) Не извлечено ни одной страницы — смотри сообщения выше.")
            print("    Диагностика структуры: scripts\\dump_help_samples.bat")
            raise SystemExit(2)
        print("\n[OK] Разбор завершён успешно.")
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        print("\n(!) Ошибка при разборе справки:")
        log_error_to_file()
        raise SystemExit(3)


if __name__ == "__main__":
    main()
