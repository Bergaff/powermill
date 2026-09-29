"""
Тесты знаний о работе технолога (пункт 48): правила, уроки и запрет облака.

Здесь важно не «работает ли файл», а обещания:
* правила и уроки читаются и попадают в ответ модели;
* похожие случаи находятся (иначе уроки бесполезны);
* пока есть знания, ответ считает ТОЛЬКО локальная модель — в облако данные не
  уходят даже при настроенном ключе (это проверяем отдельно, на src.llm и src.rag);
* пустые уроки не пишутся: Enter — и ничего не сохранилось.
"""
from __future__ import annotations

import json

import pytest

from src import knowledge


@pytest.fixture
def files(tmp_path, monkeypatch):
    """Знания — во временной папке, чтобы тесты не трогали файлы технолога."""
    monkeypatch.setattr(knowledge, "KNOWLEDGE_DIR", tmp_path / "knowledge")
    monkeypatch.setattr(knowledge, "RULES_FILE", tmp_path / "knowledge" / "rules.md")
    monkeypatch.setattr(knowledge, "LESSONS_FILE",
                        tmp_path / "knowledge" / "lessons.jsonl")
    knowledge.ensure_files()
    return tmp_path / "knowledge"


# --- правила --------------------------------------------------------------
def test_files_are_created_with_a_readable_header(files):
    text = (files / "rules.md").read_text(encoding="utf-8")
    assert "Правила работы" in text
    assert "облако" in text                     # про запрет облака сказано в шапке
    assert (files / "lessons.jsonl").exists()


def test_comment_lines_are_not_rules(files):
    for line in ("# заголовок", "", "- правило номер один", "2) правило два",
                 "* правило три"):
        with (files / "rules.md").open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    assert knowledge.load_rules() == ["правило номер один", "правило два",
                                      "правило три"]


def test_add_and_remove_rule(files):
    knowledge.add_rule("40Х, D16: S=4500 F=1200")
    knowledge.add_rule("обдирку делаю Model Area Clearance")
    assert len(knowledge.load_rules()) == 2
    assert knowledge.remove_rule(1) == "40Х, D16: S=4500 F=1200"
    assert knowledge.load_rules() == ["обдирку делаю Model Area Clearance"]


def test_empty_rule_is_refused(files):
    with pytest.raises(ValueError):
        knowledge.add_rule("   ")
    with pytest.raises(IndexError):
        knowledge.remove_rule(5)


def test_rule_is_normalised_to_one_line(files):
    knowledge.add_rule("  одно\n   правило  ")
    assert knowledge.load_rules() == ["одно правило"]


# --- уроки ----------------------------------------------------------------
def test_lesson_is_written_as_a_single_json_line(files):
    knowledge.add_lesson(problem="не заданы хвостовик и патрон",
                         fix="задал условную державку",
                         task="проверки", source="check_toolpaths",
                         when="2026-09-29 15:00")
    lines = [line for line in (files / "lessons.jsonl").read_text(encoding="utf-8")
             .splitlines() if line.strip() and not line.startswith("#")]
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["fix"] == "задал условную державку"
    assert data["source"] == "check_toolpaths"
    assert data["tags"]


def test_broken_line_does_not_break_lessons(files):
    with (files / "lessons.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{ это не json\n")
    knowledge.add_lesson(problem="ошибка", fix="исправил", when="2026-01-01 00:00")
    assert len(knowledge.load_lessons()) == 1


def test_similar_lessons_are_found_by_word_forms(files):
    """«державка» и «державку» — одно и то же слово для поиска уроков."""
    knowledge.add_lesson(problem="не заданы ни хвостовик ни патрон",
                         fix="задал условную державку",
                         task="проверки траекторий", when="2026-01-01 00:00")
    knowledge.add_lesson(problem="порвался ремень", fix="заменил",
                         task="станок", when="2026-01-02 00:00")
    found = knowledge.similar_lessons("проверка столкновений: державка")
    assert [lesson.fix for lesson in found] == ["задал условную державку"]


def test_unrelated_question_finds_nothing(files):
    knowledge.add_lesson(problem="заготовка не определена",
                         fix="сделал FORM BLOCK + BLOCK ACCEPT",
                         when="2026-01-01 00:00")
    assert knowledge.similar_lessons("алюминий припуск") == []


# --- что попадает в ответ -------------------------------------------------
def test_prompt_block_holds_rules_and_lessons(files):
    knowledge.add_rule("всегда чистовую на 0.1 мм")
    knowledge.add_lesson(problem="заготовка не определена",
                         fix="FORM BLOCK + BLOCK ACCEPT",
                         task="черновая операция", when="2026-01-01 00:00")
    block = knowledge.prompt_block("черновая операция: заготовка")
    assert "ПРАВИЛА ТЕХНОЛОГА" in block
    assert "всегда чистовую на 0.1 мм" in block
    assert "ПОХОЖИЕ СЛУЧАИ" in block
    assert "облако не отправлялись" in block


def test_prompt_block_is_empty_without_knowledge(files):
    assert knowledge.prompt_block("любой вопрос") == ""
    assert knowledge.local_only() is False


def test_any_knowledge_switches_the_local_mode_on(files):
    assert knowledge.local_only() is False
    knowledge.add_rule("правило")
    assert knowledge.local_only() is True


def test_stats_and_report(files):
    knowledge.add_rule("правило")
    knowledge.add_lesson(problem="ошибка", fix="исправление")
    data = knowledge.stats()
    assert data["rules"] == 1 and data["lessons"] == 1 and data["local_only"]
    text = knowledge.format_stats()
    assert "локальная модель" in text.lower()
    assert "в облако" in text


# --- урок после неудачного прогона ---------------------------------------
def test_ask_lesson_records_the_answer(files):
    answers = iter(["поставил державку в PowerMill вручную"])
    lesson = knowledge.ask_lesson(["державка не задана"], task="проверки",
                                  source="check_toolpaths",
                                  reader=lambda _p: next(answers),
                                  printer=lambda *_a: None)
    assert lesson is not None and lesson.fix.startswith("поставил державку")
    assert knowledge.load_lessons()[0].source == "check_toolpaths"


def test_ask_lesson_skips_empty_answer(files):
    lesson = knowledge.ask_lesson(["проблема"], reader=lambda _p: "",
                                  printer=lambda *_a: None)
    assert lesson is None
    assert knowledge.load_lessons() == []


def test_ask_lesson_is_not_called_without_problems(files):
    assert knowledge.ask_lesson([], reader=lambda _p: "что-то",
                                printer=lambda *_a: None) is None
    assert knowledge.load_lessons() == []


def test_ask_lesson_survives_closed_input(files):
    def broken(_prompt: str):
        raise EOFError

    assert knowledge.ask_lesson(["проблема"], reader=broken,
                                printer=lambda *_a: None) is None
