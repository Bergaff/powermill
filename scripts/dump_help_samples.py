"""
ДИАГНОСТИКА СПРАВКИ: показывает, что реально лежит в папке оффлайн-справки,
и складывает образцы файлов в output\\help_samples\\.

Зачем: если разбор справки даёт мало текста, нужно понять почему. Этот скрипт
печатает структуру папок и содержимое образцов (заглушка .htm и «обёрнутый»
файл wrapped-files\\*.js) — вывод можно целиком прислать в чат.

Запуск:  python -m scripts.dump_help_samples     (или scripts\\dump_help_samples.bat)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (  # noqa: E402
    HELP_DIR,
    HELP_DIR_DEFAULT_EXTRAS,
    HELP_DIR_EXTRA,
    HELP_FILES_DIR,
    HELP_WRAPPED_DIR,
    OUTPUT_DIR,
)
from src.html_parser import help_roots, pick_lang_dir  # noqa: E402
from src.toc_parser import find_toc_files, parse_toc_js  # noqa: E402

SAMPLES_DIR = OUTPUT_DIR / "help_samples"
MAX_LINES_PER_SAMPLE = 22
MAX_CHARS_PER_SAMPLE = 1400


def hr(title: str) -> None:
    print("\n" + "=" * 66)
    print(f"  {title}")
    print("=" * 66)


def dir_summary(folder: Path) -> tuple[int, list[tuple[str, int, int]]]:
    """(число файлов, [(имя, размер, строки) ...] первые 12)."""
    if not folder.is_dir():
        return 0, []
    files = [p for p in folder.rglob("*") if p.is_file()]
    rows: list[tuple[str, int, int]] = []
    for p in sorted(files, key=lambda x: x.name)[:12]:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            lines = text.count("\n") + 1
        except OSError:
            lines = -1
        rows.append((str(p.relative_to(folder)), p.stat().st_size, lines))
    return len(files), rows


def preview(path: Path, chars: int = MAX_CHARS_PER_SAMPLE) -> None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"   !! не прочитать: {e}")
        return
    print(f"\n--- {path.name}  ({path.stat().st_size} байт, {len(text)} символов)")
    body = text[:chars]
    print(body)
    if len(text) > chars:
        print(f"    ... (обрезано, всего {len(text)} символов)")


def copy_sample(src: Path, folder: Path) -> Path | None:
    try:
        dst = folder / f"{src.parent.name}__{src.name}"
        dst.write_bytes(src.read_bytes())
        return dst
    except OSError:
        return None


# расширения, которые имеет смысл разбирать как текст
TEXT_EXT = (".htm", ".html", ".txt", ".xml", ".json", ".mc", ".mac", ".pml", ".chm")


def dump_other_root(root: Path) -> None:
    """Показывает, что лежит внутри нестандартного корня (PARREF, PARSUM, DOC, HELP)."""
    hr(f"НЕСТАНДАРТНЫЙ КОРЕНЬ: {root}")
    print("  (здесь нет files/ и contexthelp/ — смотрю, что есть)")
    try:
        subdirs = sorted(p for p in root.iterdir() if p.is_dir())
    except OSError as e:
        print(f"  !! не прочитать: {e}")
        return

    for sub in subdirs:
        files = [p for p in sub.rglob("*") if p.is_file()]
        if not files:
            print(f"\n  [{sub.name}] — пусто")
            continue
        exts: dict[str, int] = {}
        for f in files:
            exts[f.suffix.lower() or "(без расширения)"] = exts.get(f.suffix.lower() or "(без расширения)", 0) + 1
        total_mb = sum(f.stat().st_size for f in files) / 1e6
        print(f"\n  [{sub.name}] файлов: {len(files)}, {total_mb:.1f} МБ")
        print("      расширения: " + ", ".join(f"{k}: {v}" for k, v in sorted(exts.items(), key=lambda kv: -kv[1])[:8]))

        biggest = sorted(files, key=lambda f: -f.stat().st_size)[:5]
        for f in biggest:
            print(f"      {f.stat().st_size:>9} байт  {f.relative_to(sub)}")

        # образец текстового файла — самое важное
        text_files = [f for f in files if f.suffix.lower() in TEXT_EXT]
        if text_files:
            sample = max(text_files, key=lambda f: f.stat().st_size)
            preview(sample, chars=900)
            copy_sample(sample, SAMPLES_DIR)
        else:
            print("      (текстовых файлов .htm/.txt/.xml не найдено)")


def main() -> None:
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    hr("1. Где ищем справку (config.py)")
    print(f"POWERMILL_HELP_DIR        = {HELP_DIR}  (есть: {HELP_DIR.exists()})")
    for extra in [*HELP_DIR_EXTRA, *HELP_DIR_DEFAULT_EXTRAS]:
        print(f"доп. корень               = {extra}  (есть: {extra.exists()})")

    roots = help_roots()
    hr("2. Найденные корни справки")
    if not roots:
        print("НЕ НАЙДЕНО НИ ОДНОЙ ПАПКИ СПРАВКИ.")
        print("Задай путь вручную, например:")
        print(r"  set POWERMILL_HELP_DIR=C:\ProgramData\Autodesk\PowerMill\2026\Help")
        print("  setx POWERMILL_HELP_DIR \"C:\\ProgramData\\Autodesk\\PowerMill\\2026\\Help\"")
        return
    for root in roots:
        lang = pick_lang_dir(root, "rus")
        print(f"  {root}\n      -> языковая папка: {lang if lang else 'НЕ НАЙДЕНА'}")

    for idx, root in enumerate(roots, 1):
        hr(f"3.{idx} Структура корня: {root}")
        try:
            for child in sorted(root.iterdir()):
                kind = "папка" if child.is_dir() else "файл"
                size = "" if child.is_dir() else f"{child.stat().st_size} байт"
                print(f"    [{kind}] {child.name} {size}")
        except OSError as e:
            print(f"    !! {e}")
            continue

        lang = pick_lang_dir(root, "rus") or root
        files_dir = lang / HELP_FILES_DIR
        wrapped_dir = lang / HELP_WRAPPED_DIR
        ctx_dir = lang / "contexthelp"
        scripts_dir = lang / "scripts"

        # Нестандартный корень (например, установка PowerMill: DOC/HELP/PARREF/PARSUM)
        if not files_dir.is_dir() and not ctx_dir.is_dir():
            dump_other_root(root)

        hr(f"3.{idx}.{1} files\\ — {lang.name}\\{HELP_FILES_DIR}")
        count, rows = dir_summary(files_dir)
        print(f"  файлов: {count}")
        for name, size, lines in rows:
            print(f"    {size:>8} байт  {lines:>5} строк  {name}")

        hr(f"3.{idx}.{2} wrapped-files\\ — где обычно лежит ТЕКСТ")
        count_w, rows_w = dir_summary(wrapped_dir)
        print(f"  файлов: {count_w}")
        for name, size, lines in rows_w:
            print(f"    {size:>8} байт  {lines:>5} строк  {name}")

        hr(f"3.{idx}.{3} contexthelp\\ (короткие подсказки-термины)")
        count_c, rows_c = dir_summary(ctx_dir)
        print(f"  файлов: {count_c}")
        for name, size, lines in rows_c[:5]:
            print(f"    {size:>8} байт  {lines:>5} строк  {name}")

        hr(f"3.{idx}.{4} scripts\\ (оглавление и поисковый индекс)")
        count_s, rows_s = dir_summary(scripts_dir)
        print(f"  файлов: {count_s}")
        for name, size, lines in rows_s:
            print(f"    {size:>8} байт  {lines:>5} строк  {name}")

        # --- образцы для отправки в чат ---
        hr(f"3.{idx}.{5} ОБРАЗЦЫ ФАЙЛОВ (полностью сохранены в {SAMPLES_DIR})")
        htm_files = sorted(files_dir.glob("*.htm")) if files_dir.is_dir() else []
        for htm in htm_files[:2]:
            preview(htm)
            copy_sample(htm, SAMPLES_DIR)
        wrapped_files = sorted(wrapped_dir.glob("*.js")) if wrapped_dir.is_dir() else []
        for js in wrapped_files[:2]:
            preview(js)
            copy_sample(js, SAMPLES_DIR)
        for toc in find_toc_files(lang)[:1]:
            preview(toc, chars=2000)
            copy_sample(toc, SAMPLES_DIR)
        ctx_files = sorted(ctx_dir.glob("*.htm")) if ctx_dir.is_dir() else []
        for ctx in ctx_files[:2]:
            preview(ctx, chars=1900)   # целиком: иначе не видно, куда ведёт редирект
            copy_sample(ctx, SAMPLES_DIR)

        toc_nodes = []
        for toc in find_toc_files(lang)[:1]:
            toc_nodes = parse_toc_js(toc.read_text(encoding="utf-8", errors="replace"))
        if toc_nodes:
            hr(f"3.{idx}.{6} Оглавление: {len(toc_nodes)} узлов, первые 15")
            for node in toc_nodes[:15]:
                print(f"    {'  ' * int(node['depth'])}{node['title'][:70]}"
                      f"   {node['href'][:50]}")

    hr("ИТОГ")
    print(f"Образцы файлов: {SAMPLES_DIR}")
    print("Пришли вывод этого скрипта в чат — по нему будет ясно, как настроить парсер.")
    print()
    print("Если в разделе 'НЕСТАНДАРТНЫЙ КОРЕНЬ' видно файлы PARREF/PARSUM —")
    print("это справочник PML; пришли его образец в чат, добавлю разбор.")


if __name__ == "__main__":
    main()
