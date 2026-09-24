"""Тесты батников: то, из-за чего у пользователя «закрывалось окно».

Проверяем правила, найденные на практике:

* переводы строк **CRLF** — с Unix-строками (LF) `cmd.exe` рвёт строки посередине
  и выдаёт обрывки вида `'ерка' is not recognized as an internal or external
  command`;
* без BOM — иначе мусор попадает в первую строку;
* `chcp 65001` — иначе русский текст в консоли превращается в крякозябры;
* никаких скобочных блоков `( ... )` с русским текстом — под chcp 65001 они
  закрывали окно у пользователя (пункты 4/5 меню);
* все `goto` имеют парные метки, а все `call` — существующие файлы;
* меню вызывает только существующие батники, и его пункты идут подряд.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", "output"}


def bat_files() -> list[Path]:
    return [p for p in sorted(ROOT.rglob("*.bat"))
            if not any(part in SKIP_DIRS for part in p.parts)]


BATS = bat_files()


def test_bat_files_found():
    assert len(BATS) >= 20, "батники должны быть в репозитории"


@pytest.mark.parametrize("path", BATS, ids=lambda p: p.name)
def test_crlf_line_endings(path: Path):
    raw = path.read_bytes()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    assert lf == 0, (f"{path.name}: {lf} строк с Unix-переводом (LF). "
                     f"cmd.exe рвёт такие строки — нужен CRLF")


@pytest.mark.parametrize("path", BATS, ids=lambda p: p.name)
def test_no_bom(path: Path):
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), \
        f"{path.name}: файл начинается с BOM"


@pytest.mark.parametrize("path", BATS, ids=lambda p: p.name)
def test_has_chcp(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    assert "chcp" in text.lower(), f"{path.name}: нет chcp 65001"


@pytest.mark.parametrize("path", BATS, ids=lambda p: p.name)
def test_no_paren_blocks_with_russian(path: Path):
    """Скобочные блоки с русским текстом — причина закрывающихся окон."""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.split("\n")
    block_open = re.compile(r"^\s*(?:if|for|else|while)\b[^\r\n]*\(\s*$")
    russian = re.compile(r"[а-яА-ЯёЁ]")

    for index, line in enumerate(lines):
        if not block_open.match(line):
            continue
        for inner in lines[index + 1:index + 40]:
            assert not russian.search(inner), (
                f"{path.name}: строка {index + 1} открывает скобочный блок "
                f"с русским текстом — переписать плоско через goto")
            if inner.strip() in (")", ") else ("):
                break


@pytest.mark.parametrize("path", BATS, ids=lambda p: p.name)
def test_goto_labels_exist(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    labels = {m.group(1).lower() for m in
              re.finditer(r"(?m)^\s*:([A-Za-z_]\w*)", text)}
    gotos = {m.group(1).lower() for m in
             re.finditer(r"(?i)\bgoto\s+:?([A-Za-z_]\w*)", text)}
    assert not (gotos - labels), f"{path.name}: goto без метки: {gotos - labels}"


@pytest.mark.parametrize("path", BATS, ids=lambda p: p.name)
def test_call_targets_exist(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    for target in re.findall(r'(?i)\bcall\s+"([^"]+)"', text):
        clean = target.replace("%~dp0", "").replace("\\", "/")
        assert (path.parent / clean).exists(), \
            f"{path.name}: call на несуществующий файл {target}"


def test_update_from_git_repairs_line_endings():
    """Обновление из Git должно само чинить переводы строк."""
    text = (ROOT / "update_from_git.bat").read_text(encoding="utf-8")
    assert "repair_bats" in text


def test_menu_items_are_sequential_and_targets_exist():
    text = (ROOT / "start_menu.bat").read_text(encoding="utf-8")
    numbers = [int(m.group(1)) for m in
               re.finditer(r"(?m)^echo\s+(\d+)\s+-", text)]
    numbered = [n for n in numbers if n != 0]      # 0 — это «выход»
    assert numbered == list(range(1, len(numbered) + 1)), \
        f"пункты меню идут не подряд: {numbers}"

    for target in re.findall(r'(?i)\bcall\s+"%~dp0([^"]+)"', text):
        clean = target.replace("\\", "/")
        assert (ROOT / clean).exists(), f"меню вызывает несуществующий {target}"


DIAGNOSTIC_BATS = ("check_pm_api.bat", "install_bridge.bat",
                   "prepare_pm_macros.bat", "show_reports.bat")


@pytest.mark.parametrize("name", DIAGNOSTIC_BATS)
def test_diagnostic_bats_always_pause(name: str):
    """Окно не должно «улетать»: результат нужно успеть прочитать.

    Раньше при запуске из меню паузы не было (PM_FROM_MENU), и технолог не
    успевал скопировать вывод — теперь пауза всегда, а отчёт сохраняется в
    файл, который открывается пунктом 29.
    """
    text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
    assert "pause" in text
    assert "PM_FROM_MENU" not in text


def test_diagnostic_bats_point_to_reports():
    for name in DIAGNOSTIC_BATS[:-1]:
        text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "29" in text, f"{name} должен подсказывать пункт 29 (отчёты)"


def test_gitattributes_forces_crlf():
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.bat" in attrs and "eol=crlf" in attrs, \
        ".gitattributes должен задавать CRLF для *.bat"
