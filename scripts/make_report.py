"""
ОТЧЁТ ДЛЯ ЧАТА: собирает всё, что нужно для диагностики, в один текстовый файл.

Пишет output\\OTCHET_DLYA_CHATA.txt: система, пути, структура справки, статистика
разбора, результаты поиска и последние ошибки. Этот файл можно целиком скопировать
в чат — по нему видно, что установлено и что не работает.

Запуск: scripts\\make_report.bat
"""
from __future__ import annotations

import json
import platform
import sqlite3
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from config import (  # noqa: E402
    CHROMA_DIR,
    CURRENT_MODE,
    DATA_ROOT,
    EMBEDDING_MODEL,
    HELP_DIR,
    HELP_DIR_DEFAULT_EXTRAS,
    HELP_DIR_EXTRA,
    HELP_LANG,
    HELP_SEARCH_DB,
    LLM_CODE_MODEL,
    LLM_MODEL,
    OUTPUT_DIR,
    PDF_DIR,
    VIDEO_DIR,
)

REPORT_FILE = OUTPUT_DIR / "OTCHET_DLYA_CHATA.txt"

MAX_LINES = 40          # сколько строк образца печатать
MAX_CHARS = 3000


class Report:
    def __init__(self) -> None:
        self.parts: list[str] = []

    def add(self, text: str = "") -> None:
        self.parts.append(text)

    def head(self, title: str) -> None:
        self.add("")
        self.add("=" * 70)
        self.add(f"  {title}")
        self.add("=" * 70)

    def lines(self, title: str, rows: list[str]) -> None:
        self.head(title)
        for row in rows:
            self.add(f"  {row}")

    def preview(self, path: Path, chars: int = MAX_CHARS) -> None:
        self.head(f"ОБРАЗЕЦ: {path.name}")
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            self.add(f"  !! не прочитать: {e}")
            return
        self.add(f"  размер: {path.stat().st_size} байт, {len(text)} символов")
        body = text[:chars]
        for line in body.splitlines()[:MAX_LINES]:
            self.add("  | " + line)
        if len(text) > chars:
            self.add(f"  | ... (обрезано, всего {len(text)} символов)")

    def save(self) -> Path:
        REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        REPORT_FILE.write_text("\n".join(self.parts), encoding="utf-8")
        return REPORT_FILE


def run_safe(cmd: list[str], cwd: Path, timeout: int = 60) -> str:
    """Запускает команду и возвращает вывод (или текст ошибки)."""
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                              timeout=timeout, encoding="utf-8", errors="replace")
        out = (proc.stdout or "") + (proc.stderr or "")
        return out.strip() or f"(пусто, код {proc.returncode})"
    except Exception as e:  # noqa: BLE001
        return f"!! ошибка запуска: {e}"


def folder_stats(path: Path) -> tuple[int, int]:
    """(файлов, суммарный размер байт)."""
    if not path.exists():
        return 0, 0
    n = 0
    size = 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                n += 1
                size += p.stat().st_size
        except OSError:
            continue
    return n, size


def main() -> int:
    rep = Report()
    rep.add("ОТЧЁТ PowerMill AI")
    rep.add(f"Сформирован: {datetime.now():%Y-%m-%d %H:%M:%S}")
    rep.add("Скопируй ЭТОТ ФАЙЛ ЦЕЛИКОМ и пришли в чат.")

    # ---------------- 1. Система ----------------
    rep.lines("1. СИСТЕМА", [
        f"ОС: {platform.platform()}",
        f"Python: {sys.version.split()[0]} ({sys.executable})",
        f"Режим приложения: {CURRENT_MODE.upper()}",
        f"Папка репозитория: {REPO_ROOT}",
    ])

    # ---------------- 2. Пути ----------------
    rep.lines("2. ПУТИ (config.py)", [
        f"DATA_ROOT (E:)      = {DATA_ROOT}   есть: {DATA_ROOT.exists()}",
        f"HELP_DIR            = {HELP_DIR}   есть: {HELP_DIR.exists()}",
        f"HELP_DIR_EXTRA      = {[str(p) for p in HELP_DIR_EXTRA]}",
        f"HELP_DIR_DEFAULT    = {[str(p) for p in HELP_DIR_DEFAULT_EXTRAS]}",
        f"HELP_LANG           = {HELP_LANG}",
        f"OUTPUT_DIR          = {OUTPUT_DIR}",
        f"CHROMA_DIR          = {CHROMA_DIR}   есть: {CHROMA_DIR.exists()}",
        f"HELP_SEARCH_DB      = {HELP_SEARCH_DB}   есть: {HELP_SEARCH_DB.exists()}",
        f"Модели: чат={LLM_MODEL}, код={LLM_CODE_MODEL}",
        f"Эмбеддинги: {EMBEDDING_MODEL}",
    ])

    # ---------------- 3. Зависимости ----------------
    import importlib.util

    modules = ["bs4", "tqdm", "psutil", "chromadb", "sentence_transformers",
               "ollama", "faster_whisper", "aiogram", "langchain_text_splitters",
               "torch", "pymupdf", "pytest"]
    status_rows = []
    for mod in modules:
        try:
            status_rows.append(f"{mod:<26} {'есть' if importlib.util.find_spec(mod) else 'НЕТ'}")
        except (ImportError, ValueError):
            status_rows.append(f"{mod:<26} НЕТ")
    rep.lines("3. БИБЛИОТЕКИ", status_rows)

    # ---------------- 4. Справка на диске ----------------
    rep.head("4. ПАПКА СПРАВКИ PowerMill")
    if HELP_DIR.exists():
        try:
            children = sorted(HELP_DIR.iterdir())
            rep.add(f"  содержимое {HELP_DIR}:")
            for child in children[:20]:
                kind = "dir " if child.is_dir() else "file"
                rep.add(f"    [{kind}] {child.name}")
        except OSError as e:
            rep.add(f"  !! не прочитать: {e}")

        from src.html_parser import help_roots, pick_lang_dir  # noqa: PLC0415

        roots = help_roots()
        for root in roots:
            lang_dir = pick_lang_dir(root, HELP_LANG)
            rep.add(f"  корень {root} -> языковая папка: {lang_dir or 'НЕ НАЙДЕНА'}")
            if lang_dir is None:
                continue
            for name in ("files", "wrapped-files", "contexthelp", "scripts"):
                n, size = folder_stats(lang_dir / name)
                rep.add(f"    {name:<14} файлов: {n:<6} размер: {size / 1e6:.1f} МБ")
            samples = sorted((lang_dir / "files").glob("*.htm"))[:1]
            samples += sorted((lang_dir / "wrapped-files").glob("*.js"))[:1]
            for sample in samples:
                rep.preview(sample)
    else:
        rep.add("  СПРАВКА НЕ НАЙДЕНА. Проверь путь: scripts\\find_help.bat, "
                "затем scripts\\set_help_path.bat")

    # ---------------- 5. Результаты разбора ----------------
    rep.head("5. РАЗБОР СПРАВКИ (output)")
    pages_file = OUTPUT_DIR / "help_pages.jsonl"
    if pages_file.exists():
        n = sum(1 for line in pages_file.read_text(encoding="utf-8").splitlines() if line.strip())
        rep.add(f"  help_pages.jsonl: {n} страниц, {pages_file.stat().st_size / 1e6:.1f} МБ")
        # первые 5 страниц: заголовок + раздел + сколько символов
        shown = 0
        for line in pages_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                page = json.loads(line)
            except json.JSONDecodeError:
                continue
            rep.add(f"    - {page.get('text_chars', 0):>6} симв.  "
                    f"{page.get('breadcrumb') or page.get('title')}   "
                    f"[{page.get('kind')}, из {page.get('extracted_from')}]")
            shown += 1
            if shown >= 5:
                break
    else:
        rep.add("  help_pages.jsonl НЕТ — справка ещё не разобрана (start_parse_help.bat)")

    report_txt = OUTPUT_DIR / "help_report.txt"
    if report_txt.exists():
        rep.head("6. ОТЧЁТ РАЗБОРА (output\\help_report.txt)")
        text = report_txt.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines()[:60]:
            rep.add("  | " + line)

    # ---------------- 7. FTS-индекс ----------------
    rep.head("7. ИНДЕКС ПОИСКА (FTS5)")
    if HELP_SEARCH_DB.exists():
        try:
            conn = sqlite3.connect(str(HELP_SEARCH_DB))
            n = conn.execute("SELECT count(*) FROM pages").fetchone()[0]
            conn.close()
            rep.add(f"  страниц в индексе: {n}, файл {HELP_SEARCH_DB.stat().st_size / 1e6:.1f} МБ")
        except sqlite3.Error as e:
            rep.add(f"  !! индекс повреждён: {e}")
    else:
        rep.add("  индекса нет (start_parse_help.bat)")

    # ---------------- 8. Пробные запросы ----------------
    rep.head("8. ПРОБНЫЕ ЗАПРОСЫ К БАЗЕ")
    rep.add(run_safe([sys.executable, "-m", "src.help_search", "чистовая обработка по кривой"],
                     REPO_ROOT))
    rep.add("")
    rep.add(run_safe([sys.executable, "-m", "src.cutting",
                      "Сталь 40Х, фреза D16, черновая"], REPO_ROOT))

    # ---------------- 9. Данные ----------------
    rep.head("9. ДАННЫЕ И РЕЗУЛЬТАТЫ")
    for name, folder in (("data\\pdf", PDF_DIR), ("data\\videos", VIDEO_DIR),
                         ("data\\macros", DATA_ROOT / "data" / "macros"),
                         ("output", OUTPUT_DIR)):
        n, size = folder_stats(folder)
        rep.add(f"  {name:<18} файлов: {n:<6} {size / 1e6:.1f} МБ")

    # ---------------- 10. Ошибки ----------------
    rep.head("10. ПОСЛЕДНИЕ ОШИБКИ (если были)")
    log_candidates = [OUTPUT_DIR / "errors.log", REPO_ROOT / "errors.log"]
    found = False
    for log in log_candidates:
        if log.exists():
            found = True
            rep.add(f"  --- {log.name} ---")
            tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
            for line in tail:
                rep.add("  | " + line)
    if not found:
        rep.add("  файлов с ошибками нет (это хорошо)")

    rep.add("")
    rep.add("=" * 70)
    rep.add("  КОНЕЦ ОТЧЁТА. Скопируй всё выше и пришли в чат.")
    rep.add("=" * 70)

    path = rep.save()
    print(f"✅ Отчёт готов: {path}")
    print(f"   Размер: {path.stat().st_size / 1024:.1f} КБ, строк: {len(rep.parts)}")
    print("   Открой его, выдели всё (Ctrl+A), скопируй (Ctrl+C) и пришли в чат.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 — отчёт должен собраться даже при сбое
        print("!! Ошибка при подготовке отчёта:")
        traceback.print_exc()
        sys.exit(1)
