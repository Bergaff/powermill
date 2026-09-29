"""Тесты словаря реального PML и проверки сгенерированных макросов.

Повод — реальный случай: на задачу «создать границы по всем отверстиям модели»
модель выдала макрос с выдуманными строками

    Create Boundary "Silhouette" $e
    Add Default Allowance $e
    Check Toolpath $e

которых в PowerMill не существует. Теперь такие строки должны быть пойманы.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src import macro_index, pml_vocab


# --------------------------------------------------------------------------
# Словарь
# --------------------------------------------------------------------------
@pytest.fixture
def vocab():
    pages = [
        {"kind": "pml", "path": "PARREF/toolpath.html",
         "text": "## SwarfBasePosition\n## LeadAngle\n## Thickness\n", "source": "a"},
        {"kind": "pml", "path": "PARREF/boundary.html",
         "text": "## BoundaryType\n", "source": "b"},
        {"kind": "pml", "path": "PARREF/tool.html",
         "text": "## Diameter\n", "source": "c"},
        {"kind": "macro", "path": "found/x.mac", "text": "// пример",
         "source": "Макросы/x.mac", "title": "Макрос: пример"},
    ]
    return pml_vocab.build_vocabulary(pages)


def test_entities_come_from_reference_file_names(vocab):
    assert "toolpath" in vocab["entities"]
    assert "boundary" in vocab["entities"]
    assert "tool" in vocab["entities"]


def test_parameters_come_from_headings(vocab):
    assert "SwarfBasePosition" in vocab["parameters"]
    assert "Thickness" in vocab["parameters"]


def test_macro_sources_are_kept(vocab):
    assert vocab["macro_sources"]
    assert vocab["macro_sources"][0]["title"] == "Макрос: пример"


def test_fallback_entities_when_no_reference_parsed():
    vocab = pml_vocab.build_vocabulary([{"kind": "page", "path": "files/x.htm", "text": ""}])
    assert "boundary" in vocab["entities"]
    assert "toolpath" in vocab["entities"]


def test_save_and_load_vocabulary(tmp_path, monkeypatch):
    monkeypatch.setattr(pml_vocab, "VOCAB_FILE", tmp_path / "v.json")
    monkeypatch.setattr(pml_vocab, "VOCAB_TEXT", tmp_path / "v.txt")
    vocab = {"entities": ["boundary", "toolpath"], "parameters": ["Thickness"],
             "macro_sources": [], "built_from_pages": 2}
    pml_vocab.save_vocabulary(vocab)
    assert (tmp_path / "v.txt").read_text(encoding="utf-8").count("boundary") >= 1

    monkeypatch.setattr(pml_vocab, "VOCAB_FILE", tmp_path / "v.json")
    loaded = pml_vocab.load_vocabulary()
    assert loaded["entities"] == ["boundary", "toolpath"]


def test_load_vocabulary_without_file_gives_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(pml_vocab, "VOCAB_FILE", tmp_path / "нет.json")
    loaded = pml_vocab.load_vocabulary()
    assert "toolpath" in loaded["entities"]


# --------------------------------------------------------------------------
# Подбор имён под задачу
# --------------------------------------------------------------------------
def test_relevant_entities_understands_russian(vocab):
    names = pml_vocab.relevant_entities("создать границы по всем отверстиям модели", vocab)
    assert names[0] == "boundary"


def test_relevant_parameters_prefer_hits(vocab):
    hits = [{"text": "## Thickness\n## BoundaryType\nтекст"}]
    params = pml_vocab.relevant_parameters("припуск", hits, vocab)
    assert "Thickness" in params


# --------------------------------------------------------------------------
# Проверка макроса: плохой пример
# --------------------------------------------------------------------------
BAD_MACRO = """// Создание границы по силуэту для всех отверстий модели
FOREACH $e IN FOLDER("Model") {
    IF $e.Type == "Hole" {
        Create Boundary "Silhouette" $e
    }
}
FOREACH $e IN FOLDER("Toolpaths") {
    Check Toolpath $e
}
"""


def test_bad_macro_is_flagged(vocab):
    report = pml_vocab.validate(BAD_MACRO, vocab)
    assert report["ok"] is False
    assert report["case_errors"], "Create Boundary — команда не заглавными буквами"
    assert report["not_commands"], "Check Toolpath — не команда PML"
    assert report["bad_types"], 'Type == "Hole" — такого типа нет в документации'


def test_check_format_mentions_specific_lines(vocab):
    text = pml_vocab.format_check(pml_vocab.validate(BAD_MACRO, vocab))
    assert "Check Toolpath" in text
    assert "PML различает регистр" in text


def test_comments_and_strings_are_not_checked(vocab):
    code = """// здесь Create Boundary "Silhouette" — просто комментарий
PRINT "любой текст с Toolpath и BOUNDARY"
"""
    report = pml_vocab.validate(code, vocab)
    assert report["ok"] is True


GOOD_MACRO = """// припуск по границам
FOREACH $b IN FOLDER("Boundary") {
    EDIT BOUNDARY $b.name ; PARAMETERS THICKNESS 0.5
}
"""


def test_good_macro_passes(vocab):
    report = pml_vocab.validate(GOOD_MACRO, vocab)
    assert report["ok"] is True


def test_case_sensitive_variable_names_are_fine(vocab):
    """Переменные и имена в кавычках не должны считаться командами."""
    code = '$MyVar = "Toolpath"\nPRINT $MyVar\n'
    report = pml_vocab.validate(code, vocab)
    assert not report["not_commands"]


# --------------------------------------------------------------------------
# Макросы с диска
# --------------------------------------------------------------------------
def test_collect_macros_from_folder(tmp_path):
    folder = tmp_path / "macros"
    (folder / "found").mkdir(parents=True)
    (folder / "found" / "demo.mac").write_text(
        "// Пример: припуск по границе\nEDIT BOUNDARY $b.name ; PARAMETERS THICKNESS 0.5\n",
        encoding="utf-8")
    (folder / "пусто.mac").write_text("", encoding="utf-8")

    pages = macro_index.collect(folder)
    assert len(pages) == 1
    page = pages[0]
    assert page["kind"] == "macro"
    assert "припуск по границе" in page["breadcrumb"]
    assert page["priority"] < 0.5        # макрос важнее справочника параметров
    assert "EDIT BOUNDARY" in page["text"]


def test_describe_without_comment_uses_file_name(tmp_path):
    path = tmp_path / "no_comment.mac"
    path.write_text("PRINT \"привет\"\n", encoding="utf-8")
    page = macro_index.describe(path)
    assert page is not None
    assert "no_comment" in page["title"]


def test_macro_entities_feed_vocabulary(tmp_path):
    """Имена из настоящих макросов должны пополнять словарь PML."""
    pages = macro_index.collect(tmp_path)  # пусто
    assert pages == []


# --------------------------------------------------------------------------
# Сквозная проверка: чат-команда /macro
# --------------------------------------------------------------------------
def test_macro_command_reports_and_saves(tmp_path, monkeypatch):
    """Полный путь /macro: подсказка с именами -> генерация -> проверка -> файл."""
    import config
    from src import rag

    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(pml_vocab, "VOCAB_FILE", tmp_path / "vocab.json")
    monkeypatch.setattr(pml_vocab, "VOCAB_TEXT", tmp_path / "vocab.txt")

    seen: dict = {}

    def fake_generate(self, model, prompt, temperature=0.2, **kwargs):
        seen["prompt"] = prompt
        return "```pml\n" + BAD_MACRO + "\n```"

    monkeypatch.setattr(rag.PowerMillAI, "_generate", fake_generate)
    monkeypatch.setattr(rag.PowerMillAI, "_retrieve", lambda self, q, top_k=None: [])

    ai = rag.PowerMillAI(store=object(), load_fts=False, verbose=False)
    out = ai.macro("создать границы по всем отверстиям модели")

    # в подсказку модели попал словарь проверенных имён и правило про регистр
    assert "ПРОВЕРЕННЫЕ ИМЕНА" in seen["prompt"]
    assert "ЗАГЛАВНЫМИ" in seen["prompt"]

    # в ответе — конкретные подозрительные строки, а не общее «проверь синтаксис»
    assert "Check Toolpath" in out
    assert "НЕЛЬЗЯ верить" in out

    # файл сохранён с шапкой-предупреждением
    saved = list((tmp_path / "macros").glob("*.mac"))
    assert saved, "макрос должен сохраниться"
    content = saved[0].read_text(encoding="utf-8")
    assert "ВНИМАНИЕ" in content
    assert "// Задача:" in content
    assert "Check Toolpath" in content


def test_macro_saved_header_is_clean_for_good_macro(tmp_path, monkeypatch):
    import config
    from src import rag

    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(pml_vocab, "VOCAB_FILE", tmp_path / "v.json")
    monkeypatch.setattr(pml_vocab, "VOCAB_TEXT", tmp_path / "v.txt")
    monkeypatch.setattr(rag.PowerMillAI, "_generate",
                        lambda self, m, p, temperature=0.2, **k: "```pml\n" + GOOD_MACRO + "\n```")
    monkeypatch.setattr(rag.PowerMillAI, "_retrieve", lambda self, q, top_k=None: [])

    ai = rag.PowerMillAI(store=object(), load_fts=False, verbose=False)
    ai.macro("припуск по границам")
    saved = list((tmp_path / "macros").glob("*.mac"))[0].read_text(encoding="utf-8")
    assert "подозрительных строк нет" in saved
    assert "ВНИМАНИЕ" not in saved
