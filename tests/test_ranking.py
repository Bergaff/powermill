"""Тесты: разбиение гигантских страниц и ранжирование по источнику.

Сценарий из практики: в справочнике PowerMill есть статья руководства про
Swarf, и есть параметрический справочник PML (PARREF) — таблица на 575 000
символов, где слово «swarf» встречается сотни раз. Без разбиения и приоритетов
поиск выдавал только таблицу, а статью руководства — нет.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.help_search import HelpSearch
from src.html_parser import (
    SOURCE_PRIORITY,
    pml_section_and_title,
    split_page_text,
)


# --------------------------------------------------------------------------
# Разбиение длинных страниц
# --------------------------------------------------------------------------
def _long_text(sections: int = 40, per_section: int = 800) -> str:
    parts = ["# Справочник параметров"]
    for i in range(sections):
        parts.append(f"## Раздел {i}")
        parts.append("строка параметров " * (per_section // 18))
    return "\n".join(parts)


def test_short_text_is_not_split():
    parts = split_page_text("# Заголовок\n\nнемного текста")
    assert len(parts) == 1
    assert parts[0][0] == ""


def test_long_text_splits_by_sections():
    text = _long_text()
    parts = split_page_text(text, max_chars=5000)
    assert len(parts) > 3
    # каждая часть — не больше лимита с небольшим запасом
    assert all(len(p) <= 5000 * 1.2 for _t, p in parts)
    # подзаголовки взяты из разделов
    titles = [t for t, _p in parts if t]
    assert any(t.startswith("Раздел") for t in titles)
    # ни одна часть не потерялась целиком: суммарно текст сопоставим
    assert sum(len(p) for _t, p in parts) >= len(text) * 0.9


def test_split_parts_have_no_empty_tail():
    text = _long_text(sections=10, per_section=1000)
    parts = split_page_text(text, max_chars=3000)
    assert all(p.strip() for _t, p in parts)


# --------------------------------------------------------------------------
# Заголовки и разделы справочника PML
# --------------------------------------------------------------------------
def test_pml_section_and_title_replaces_generic_title(tmp_path):
    root = tmp_path / "C"
    (root / "PARREF").mkdir(parents=True)
    file = root / "PARREF" / "toolpath_swarf.html"
    file.write_text("<html></html>", encoding="utf-8")
    body = "# toolpath\n\n## SwarfBasePosition\n\nActive if: Strategy==swarf\n"
    section, title = pml_section_and_title(root, file, body, "PowerMill Parameter Reference")
    assert section == "Справочник параметров PML"
    assert "SwarfBasePosition" in title
    assert "toolpath_swarf" in title          # имя файла для однозначности


def test_pml_title_uses_stem_without_heading(tmp_path):
    root = tmp_path / "C"
    (root / "PARSUM").mkdir(parents=True)
    file = root / "PARSUM" / "parameters.html"
    file.write_text("<html></html>", encoding="utf-8")
    section, title = pml_section_and_title(root, file, "просто текст", "PowerMill Parameter Summary")
    assert section == "Сводка параметров PML"
    assert "Parameters" in title or "parameters" in title


def test_source_priority_order():
    # руководство важнее справочника параметров
    assert SOURCE_PRIORITY["page"] < SOURCE_PRIORITY["contexthelp"] < SOURCE_PRIORITY["pml"]


# --------------------------------------------------------------------------
# Ранжирование в поиске
# --------------------------------------------------------------------------
@pytest.fixture
def rank_index(tmp_path):
    """Индекс: маленькая статья руководства + гигантская таблица параметров."""
    pages = [
        {
            "source": "l.rus/files/GUID-SWARF.htm",
            "title": "Обработка Swarf",
            "breadcrumb": "Стратегии обработки > Обработка Swarf",
            "kind": "page",
            "priority": SOURCE_PRIORITY["page"],
            "text": "# Обработка Swarf\n\nСтратегия Swarf обрабатывает вертикальные стенки.",
        },
    ]
    # справочник параметров: слово swarf встречается очень много раз
    big_rows = "\n".join(
        f"## Param{i}\nActive if: ((Strategy=='swarf' OR Strategy=='wireframe_swarf') AND X{i}==plane)"
        for i in range(300)
    )
    for part in (1, 2):
        pages.append({
            "source": f"C/PARREF/toolpath_swarf.html (часть {part}/2)",
            "title": f"toolpath (toolpath_swarf) · SwarfBasePosition",
            "breadcrumb": "Справочник параметров PML > toolpath",
            "kind": "pml",
            "priority": SOURCE_PRIORITY["pml"],
            "text": big_rows,
        })

    hs = HelpSearch(db_path=tmp_path / "rank.db", pages_file=tmp_path / "none.jsonl")
    hs.build(pages=pages, verbose=False)
    return hs


def test_guide_article_ranks_above_parameter_reference(rank_index):
    hits = rank_index.search("swarf", top_k=5)
    assert hits
    assert hits[0]["source"].startswith("l.rus/files/"), \
        "статья руководства должна быть выше таблицы параметров"


def test_parameter_reference_is_still_findable(rank_index):
    hits = rank_index.search("SwarfBasePosition", top_k=5)
    assert hits
    assert "PARREF" in hits[0]["source"]


def test_exact_parameter_name_wins_over_guide(rank_index):
    """Точное имя параметра из справочника должно находить справочник."""
    hits = rank_index.search("Param250", top_k=5)
    assert hits
    assert "PARREF" in hits[0]["source"]
