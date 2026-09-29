"""Тесты команд ассистента (/ask, /macro, /error, /compare, /sources, /stats).

Ollama и ChromaDB подменяются заглушками — проверяем логику, а не модель.
"""
from __future__ import annotations

import pytest

from src.help_search import HelpSearch
from src.rag import (
    PowerMillAI,
    extract_code,
    handle_command,
    save_macro,
    split_compare,
)


class FakeStore:
    def __init__(self, hits=None):
        self.hits = hits if hits is not None else [
            {"source": "l.rus/files/GUID-0001.htm", "text": "Стратегия Swarf для вертикальных стенок.",
             "title": "Чистовая обработка по кривой", "breadcrumb": "Стратегии обработки > Чистовая обработка по кривой",
             "kind": "page", "source_type": "help", "distance": 0.21, "found_by": "vector"},
        ]
        self.count_calls = 0

    def search(self, query, top_k=4, where=None):
        return self.hits[:top_k]

    def stats(self):
        return {"total": len(self.hits), "by_type": {"help": len(self.hits)}, "path": "/tmp/chroma"}


@pytest.fixture
def ai(parsed_pages):
    hs = HelpSearch()
    hs.ensure_index()
    instance = PowerMillAI(store=FakeStore(), fts=hs, verbose=False)
    instance._generate = lambda model, prompt, **kw: "ТЕСТ-ОТВЕТ [1]"
    return instance


def test_split_compare_variants():
    assert split_compare("Чем Model Area Clearance отличается от Offset Area?") == (
        "Model Area Clearance", "Offset Area")
    assert split_compare("compare A vs B") == ("A", "B")
    assert split_compare("A и B") == ("A", "B")
    assert split_compare("просто вопрос без сравнения")[1] == ""


def test_extract_code_prefers_longest_fenced_block():
    text = "вот код:\n```\n$a = 1;\n```\nи ещё:\n```pml\n$a = 2;\n$b = 3;\n```"
    assert extract_code(text).startswith("$a = 2;")


def test_extract_code_without_fences_returns_text():
    assert extract_code("  $a = 1;  ") == "$a = 1;"


def test_save_macro_creates_file(parsed_pages):
    path = save_macro("```\n$a = 1;\n```", "создать границы по отверстиям")
    assert path is not None and path.exists()
    assert path.suffix == ".mac"
    assert "$a = 1;" in path.read_text(encoding="utf-8")
    assert "создать_границы" in path.name


def test_ask_includes_sources(ai):
    answer = ai.ask("как сделать чистовую по кривой")
    assert "ТЕСТ-ОТВЕТ" in answer
    assert "📚 Источники" in answer


def test_macro_saves_file_and_reports_path(ai):
    answer = ai.macro("создать границы по отверстиям")
    assert "PML-макрос" in answer
    assert "💾 Сохранён файл" in answer


def test_cutting_command_has_no_llm_dependency(ai):
    text = ai.cutting_answer("Сталь 40Х, фреза D16 Sandvik, черновая")
    assert "S (об/мин)" in text and "Стратегия PowerMill" in text


def test_error_command_reports_cause_structure(ai):
    text = ai.error("Toolpath calculation failed - undercut")
    assert "ТЕСТ-ОТВЕТ" in text
    assert "📚 Источники" in text


def test_compare_command_uses_both_objects(ai):
    text = ai.compare("Чем Model Area Clearance отличается от Offset Area Clearance")
    assert "ТЕСТ-ОТВЕТ" in text


def test_compare_without_second_object_asks_for_it(ai):
    assert "Не понял" in ai.compare("просто одна стратегия")


def test_sources_debug_lists_hits(ai):
    text = ai.sources("чистовая по кривой", top_k=3)
    assert "Найдено для" in text
    assert "Порог релевантности" in text


def test_stats_reports_vector_and_fts(ai):
    text = ai.stats()
    assert "Векторная база" in text
    assert "FTS-индекс" in text


def test_handle_command_unknown_question_goes_to_ask(ai, capsys):
    assert handle_command("как задать врезание", ai) is True
    out = capsys.readouterr().out
    assert "ТЕСТ-ОТВЕТ" in out


def test_handle_command_exit(ai):
    assert handle_command("/exit", ai) is False


def test_handle_command_help(ai, capsys):
    assert handle_command("/help", ai) is True
    assert "/cutting" in capsys.readouterr().out


def test_handle_command_cutting(ai, capsys):
    handle_command("/cutting Сталь 40Х фреза D16 черновая", ai)
    assert "S (об/мин)" in capsys.readouterr().out


def test_handle_command_macro_without_task(ai, capsys):
    handle_command("/macro", ai)
    assert "Укажи задачу" in capsys.readouterr().out


def test_handle_command_sources_without_query(ai, capsys):
    handle_command("/sources", ai)
    assert "Использование" in capsys.readouterr().out
