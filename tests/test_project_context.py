"""Тесты контекста проекта PowerMill (шаг 2.0 плана)."""
from __future__ import annotations

import pytest

from src import project_context as pc

PROBE_OUTPUT = """--- POWERMILL AI PROBE START ---
MODELS:
Blok_40X
BOUNDARIES:
Boundary 1
Boundary 2
Boundary 3
Obrabotka_chernovaya
TOOLS:
Tool 1
D16_R3
TOOLPATHS:
Toolpath 1
Toolpath 2
Rough_D16
WORKPLANES:
NC PROGRAMS:
--- POWERMILL AI PROBE END ---
"""

KV_OUTPUT = """MODEL=Blok
BOUNDARY=Kontur
TOOLPATH=Rough
"""


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "CONTEXT_FILE", tmp_path / "project_context.json")
    monkeypatch.setattr(pc, "DUMP_FILE", tmp_path / "project_dump.txt")
    return tmp_path


# --------------------------------------------------------------------------
# Разбор
# --------------------------------------------------------------------------
def test_parse_probe_sections():
    data = pc.parse_dump(PROBE_OUTPUT)
    assert data["models"] == ["Blok_40X"]
    assert data["boundaries"] == ["Boundary 1", "Boundary 2", "Boundary 3",
                                  "Obrabotka_chernovaya"]
    assert data["tools"] == ["Tool 1", "D16_R3"]
    assert data["toolpaths"] == ["Toolpath 1", "Toolpath 2", "Rough_D16"]
    assert data["_total"] == 10


def test_parse_empty_sections_are_skipped():
    data = pc.parse_dump(PROBE_OUTPUT)
    assert "workplanes" not in data        # раздел был пустой
    assert "ncprograms" not in data


def test_parse_key_value_format():
    data = pc.parse_dump(KV_OUTPUT)
    assert data["models"] == ["Blok"]
    assert data["boundaries"] == ["Kontur"]
    assert data["toolpaths"] == ["Rough"]


def test_parse_ignores_noise_lines():
    text = "--- POWERMILL AI PROBE START ---\n// комментарий\nPRINT \"MODELS:\"\nMODELS:\nDetal\n"
    data = pc.parse_dump(text)
    assert data["models"] == ["Detal"]


def test_parse_unknown_lines_are_kept_for_diagnostics():
    data = pc.parse_dump("Что-то непонятное\nЕщё строка\n")
    assert data["_total"] == 0
    assert len(data["_unparsed"]) == 2


def test_parse_russian_headers():
    text = "МОДЕЛИ:\nДеталь\nГРАНИЦЫ:\nКонтур\nИНСТРУМЕНТЫ:\nD16\n"
    data = pc.parse_dump(text)
    assert data["models"] == ["Деталь"]
    assert data["boundaries"] == ["Контур"]
    assert data["tools"] == ["D16"]


# --------------------------------------------------------------------------
# Хранение и вывод
# --------------------------------------------------------------------------
def test_save_load_clear(context):
    data = pc.parse_dump(PROBE_OUTPUT)
    pc.save(data)
    assert pc.load()["models"] == ["Blok_40X"]
    pc.clear()
    assert pc.load() is None


def test_summary_lists_sections():
    text = pc.summary(pc.parse_dump(PROBE_OUTPUT))
    assert "Модели (1): Blok_40X" in text
    assert "Границы (4)" in text


def test_summary_without_context_explains_how_to_load():
    text = pc.summary(None)
    assert "пункт 24" in text


def test_prompt_block_has_real_names():
    block = pc.to_prompt_block(pc.parse_dump(PROBE_OUTPUT))
    assert 'Rough_D16' in block
    assert 'Blok_40X' in block
    assert "Проект технолога" in block


def test_prompt_block_empty_without_context():
    assert pc.to_prompt_block(None) == ""


# --------------------------------------------------------------------------
# Проверки проекта
# --------------------------------------------------------------------------
def test_checks_placeholder_names():
    items = pc.checks(pc.parse_dump(PROBE_OUTPUT))
    text = " ".join(i["text"] for i in items)
    assert "заглушек" in text


def test_checks_toolpaths_without_ncprograms():
    items = pc.checks(pc.parse_dump(PROBE_OUTPUT))
    assert any("NC-программ нет" in i["text"] for i in items)


def test_checks_toolpaths_without_tools():
    data = pc.parse_dump("MODELS:\nDetal\nTOOLPATHS:\nRough\n")
    items = pc.checks(data)
    assert any(i["level"] == "warn" and "инструментов нет" in i["text"]
               for i in items)


def test_checks_duplicate_names():
    data = pc.parse_dump("TOOLS:\nD16\nd16\n")
    items = pc.checks(data)
    assert any("Повторяющиеся" in i["text"] for i in items)


def test_checks_clean_project_gives_note():
    data = pc.parse_dump("MODELS:\nDetal\n")
    items = pc.checks(data)
    assert items and all(i["level"] == "note" for i in items)


def test_format_checks_renders_hints():
    text = pc.format_checks(pc.parse_dump(PROBE_OUTPUT))
    assert "🔍 Проверка проекта" in text
    assert "→" in text
