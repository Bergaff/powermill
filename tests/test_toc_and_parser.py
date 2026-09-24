"""Тесты разбора оглавления и общей сборки страниц справки."""
from __future__ import annotations

import json
from pathlib import Path

from src.toc_parser import build_toc_map, load_toc, normalize_href, parse_toc_js

FIXTURE = Path(__file__).parent / "fixture_help"


def test_normalize_href():
    assert normalize_href("./files/GUID-1.htm") == "files/guid-1.htm"
    assert normalize_href(r"files\GUID-1.htm#anchor") == "files/guid-1.htm"
    assert normalize_href("") == ""


def test_parse_toc_nesting_and_path():
    text = (FIXTURE / "l.rus" / "scripts" / "toc-treedata.js").read_text(encoding="utf-8")
    nodes = parse_toc_js(text)
    assert len(nodes) == 10

    by_title = {n["title"]: n for n in nodes}
    assert by_title["Чистовая обработка по кривой"]["path"] == [
        "Стратегии обработки", "Чистовая обработка по кривой",
    ]
    assert by_title["5-осевая обработка"]["path"] == [
        "Стратегии обработки", "5-осевая обработка",
    ]
    assert by_title["Установка домашней папки"]["path"] == [
        "Начало работы", "Введение", "Установка домашней папки",
    ]
    # порядок узлов сохраняется (нужен для порядка чанков в базе)
    assert nodes[0]["title"].startswith("Добро пожаловать")


def test_build_toc_map_gives_breadcrumbs():
    text = (FIXTURE / "l.rus" / "scripts" / "toc-treedata.js").read_text(encoding="utf-8")
    toc = build_toc_map(parse_toc_js(text))
    entry = toc["files/guid-0004.htm"]
    assert entry["title"] == "Установка домашней папки"
    assert entry["breadcrumb"] == ["Начало работы", "Введение"]
    assert entry["order"] < toc["contexthelp/ctx-0001.htm"]["order"]


def test_load_toc_reads_all_roots():
    toc, nodes = load_toc([FIXTURE / "l.rus"])
    assert len(nodes) == 10
    assert "files/guid-0001.htm" in toc


def test_parse_all_help_extracts_every_page(parsed_pages):
    assert len(parsed_pages) == 6
    titles = {p["title"] for p in parsed_pages}
    assert "Чистовая обработка по кривой" in titles
    assert "Создание границы по отверстиям" in titles
    assert "Добро пожаловать в справку по PowerMill." in titles
    assert "3D выборка" in titles


def test_parse_all_help_uses_only_requested_language(parsed_pages):
    # В фикстуре есть l.enu с дублем — он не должен попасть в базу
    assert all(p["root"] == "l.rus" for p in parsed_pages)
    assert not any("English duplicate" in p["text"] for p in parsed_pages)


def test_parse_all_help_uses_wrapped_files(parsed_pages):
    page = next(p for p in parsed_pages if p["title"] == "Чистовая обработка по кривой")
    # .htm-заглушка содержит только скрипты, текст берётся из wrapped-files
    assert page["extracted_from"].startswith("wrapped")
    assert page["text_chars"] > 300
    assert "Swarf" in page["text"]


def test_parse_all_help_marks_contexthelp(parsed_pages):
    ctx = [p for p in parsed_pages if p["kind"] == "contexthelp"]
    assert len(ctx) == 1
    assert ctx[0]["title"] == "3D выборка"


def test_parse_all_help_writes_jsonl_and_report(parsed_pages):
    from config import OUTPUT_DIR

    pages_file = OUTPUT_DIR / "help_pages.jsonl"
    report = OUTPUT_DIR / "help_report.txt"
    toc_txt = OUTPUT_DIR / "help_toc.txt"
    assert pages_file.exists() and report.exists() and toc_txt.exists()

    rows = [json.loads(ln) for ln in pages_file.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 6
    assert all({"source", "title", "breadcrumb", "text"} <= set(r) for r in rows)
    assert "ОТЧЁТ" in report.read_text(encoding="utf-8")
    assert "Чистовая обработка по кривой" in toc_txt.read_text(encoding="utf-8")


def test_parse_all_help_respects_limit(parsed_pages):
    from src.html_parser import parse_all_help

    pages = parse_all_help(limit=2, roots=[FIXTURE])
    assert len(pages) == 2


def test_contexthelp_term_becomes_alias_of_article(parsed_pages):
    """Термин-редирект из contexthelp привязывается к статье алиасом."""
    page = next(p for p in parsed_pages if p["title"] == "Чистовая обработка по кривой")
    assert "Обработка по кривой" in (page.get("aliases") or [])


def test_parse_all_help_reads_contextid(parsed_pages):
    page = next(p for p in parsed_pages if p["title"] == "Чистовая обработка по кривой")
    assert page["contextid"] == "SWARFFINISHING"
    assert page["topic_type"] == "concept"


def test_redirect_pages_are_not_stored_as_separate_articles(parsed_pages):
    """Страница-редирект не должна становиться «статьёй» без содержимого."""
    assert not any(p.get("kind") == "redirect" and p.get("text") for p in parsed_pages)
