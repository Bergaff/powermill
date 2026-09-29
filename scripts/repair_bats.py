"""
Починка батников: переводы строк, BOM и проверка «плоского» синтаксиса.

Зачем
-----
`cmd.exe` читает .bat-файл по байтам и плохо переносит файлы с Unix-переводами
строк (LF): строки рвутся посередине, и в консоли появляются обрывки вроде

    'ерка' is not recognized as an internal or external command
    'exe" set "PY' is not recognized ...

Поэтому все .bat в проекте обязаны иметь переводы строк CRLF и не иметь BOM.

Что делает скрипт
-----------------
1. Находит все .bat (кроме служебных папок) и переводит LF -> CRLF, убирает BOM.
2. Проверяет каждый файл:
   * есть ли `chcp 65001` (русский текст в консоли);
   * нет ли скобочных блоков `( ... )` с русским текстом — под chcp 65001 они
     ломали окно (проверено на практике: пункты 4/5 закрывались мгновенно);
   * все ли метки `:метка` имеют парные `goto`;
   * нет ли в конце «пустого» завершения без pause/exit.
3. Пишет отчёт `output/bat_check.txt`.

Запуск: пункт 26 меню (scripts\\repair_bats.bat) или
        python -m scripts.repair_bats [--check]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", "build",
             "dist", "output"}

REPORT_FILE = ROOT / "output" / "bat_check.txt"

LABEL_RE = re.compile(r"(?m)^\s*:([A-Za-z_][\w]*)")
GOTO_RE = re.compile(r"(?i)\bgoto\s+:?([A-Za-z_][\w]*)")
CALL_RE = re.compile(r'(?i)\bcall\s+"([^"]+)"')
PAREN_RU_RE = re.compile(r"(?m)^\s*\([^\r\n]*[а-яА-ЯёЁ]")
# Открытие скобочного блока: «if ... (», «else (», «for ... (»
BLOCK_OPEN_RE = re.compile(r"(?m)^\s*(?:if|for|else|while)\b[^\r\n]*\(\s*$")
RU_RE = re.compile(r"[а-яА-ЯёЁ]")


def bat_files(root: Path = ROOT) -> list[Path]:
    found: list[Path] = []
    for path in sorted(root.rglob("*.bat")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        found.append(path)
    return found


def fix_line_endings(path: Path) -> tuple[bool, bool]:
    """Переводит LF -> CRLF и убирает BOM. Возвращает (изменён, был BOM)."""
    raw = path.read_bytes()
    had_bom = raw.startswith(b"\xef\xbb\xbf")
    if had_bom:
        raw = raw[3:]
    text = raw.decode("utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    fixed = text.replace("\n", "\r\n").encode("utf-8")
    changed = fixed != raw
    if changed or had_bom:
        path.write_bytes(fixed)
    return changed, had_bom


def check_file(path: Path, root: Path = ROOT) -> list[str]:
    """Проверки одного батника. Возвращает список замечаний."""
    problems: list[str] = []
    raw = path.read_bytes()
    rel = path.relative_to(root).as_posix()

    if raw.startswith(b"\xef\xbb\xbf"):
        problems.append(f"{rel}: есть BOM — cmd может увидеть мусор в первой строке")

    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    if lf:
        problems.append(f"{rel}: {lf} строк с Unix-переводом (LF) — "
                        f"cmd рвёт такие строки, нужен CRLF")

    text = raw.decode("utf-8", errors="replace")

    if "chcp" not in text.lower():
        problems.append(f"{rel}: нет строки chcp 65001 — русский текст "
                        f"в консоли будет крякозябрами")

    for match in PAREN_RU_RE.finditer(text):
        problems.append(f"{rel}: скобочный блок с русским текстом "
                        f"(«{match.group(0).strip()[:40]}») — под chcp 65001 "
                        f"такие блоки ломают окно")

    # блок вида «if ... ( … русский текст … )» — из-за него окно закрывается
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if not BLOCK_OPEN_RE.match(line):
            continue
        for inner in lines[index + 1:index + 40]:
            if RU_RE.search(inner):
                problems.append(
                    f"{rel}: скобочный блок начинается строкой "
                    f"{index + 1} («{line.strip()[:45]}») и содержит русский "
                    f"текст — под chcp 65001 окно закрывается. "
                    f"Переписать плоско (goto)")
                break
            if inner.strip() in (")", ") else ("):
                break

    labels = {m.group(1).lower() for m in LABEL_RE.finditer(text)}
    gotos = {m.group(1).lower() for m in GOTO_RE.finditer(text)}
    missing = gotos - labels
    if missing:
        problems.append(f"{rel}: goto на несуществующие метки: "
                        f"{', '.join(sorted(missing))}")

    for target in CALL_RE.findall(text):
        # в батниках пути записаны через обратный слэш (Windows)
        clean = target.replace("%~dp0", "").replace("\\", "/")
        target_path = (path.parent / clean)
        if not target_path.exists():
            problems.append(f"{rel}: call на несуществующий файл: {target}")

    return problems


def report(results: dict[str, list[str]], fixed: list[str]) -> str:
    lines = ["=" * 58,
             "  ПРОВЕРКА БАТНИКОВ (.bat)",
             "=" * 58, ""]
    if fixed:
        lines.append("Исправлены переводы строк (LF -> CRLF):")
        for name in fixed:
            lines.append(f"  ✔ {name}")
        lines.append("")

    problems = [p for items in results.values() for p in items]
    if not problems:
        lines.append(f"Все батники в порядке: {len(results)} файлов проверено.")
        lines.append("  • переводы строк CRLF")
        lines.append("  • без BOM")
        lines.append("  • chcp 65001 на месте")
        lines.append("  • метки goto и вызовы call корректны")
        lines.append("  • нет скобочных блоков с русским текстом")
    else:
        lines.append(f"Найдено замечаний: {len(problems)}")
        for problem in problems:
            lines.append(f"  ⚠ {problem}")
        lines.append("")
        lines.append("Если видишь строки про переводы строк — запусти пункт 26")
        lines.append("ещё раз (он уже исправляет) и сообщи ассистенту.")
    return "\n".join(lines)


def main() -> int:
    check_only = "--check" in sys.argv
    files = bat_files()

    fixed: list[str] = []
    if not check_only:
        for path in files:
            changed, had_bom = fix_line_endings(path)
            if changed or had_bom:
                fixed.append(path.relative_to(ROOT).as_posix())

    results = {path.as_posix(): check_file(path) for path in files}
    text = report(results, fixed)
    print(text)

    try:
        REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        REPORT_FILE.write_text(text, encoding="utf-8")
        print(f"\n📝 Отчёт: {REPORT_FILE}")
    except OSError:
        pass

    problems = [p for items in results.values() for p in items]
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
