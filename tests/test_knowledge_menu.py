"""
Тесты пункта 48 (scripts/knowledge.py): меню правил и уроков.

Проверяем то, что важно для технолога: пункт показывает знания, добавляет,
удаляет и не пишет пустое. Файлы — во временной папке (настоящие не трогаем).
"""
from __future__ import annotations

import pytest

from scripts import knowledge as menu
from src import knowledge


@pytest.fixture
def files(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge, "KNOWLEDGE_DIR", tmp_path / "knowledge")
    monkeypatch.setattr(knowledge, "RULES_FILE", tmp_path / "knowledge" / "rules.md")
    monkeypatch.setattr(knowledge, "LESSONS_FILE",
                        tmp_path / "knowledge" / "lessons.jsonl")
    knowledge.ensure_files()
    return tmp_path / "knowledge"


class Screen:
    """Собирает то, что пункт напечатал (вместо настоящей консоли)."""

    def __init__(self):
        self.lines: list[str] = []

    def __call__(self, text: str = "") -> None:
        self.lines.append(str(text))

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def scripted(answers: list[str]):
    queue = list(answers)

    def reader(_prompt: str = ""):
        return queue.pop(0) if queue else ""

    return reader


def test_add_rule_from_the_menu(files):
    screen = Screen()
    assert menu.add_rule_dialog(reader=scripted(["D16: S=4500 F=1200"]),
                                printer=screen)
    assert knowledge.load_rules() == ["D16: S=4500 F=1200"]
    assert "локальная модель" in screen.text        # про облако сказано сразу


def test_empty_rule_is_not_written(files):
    screen = Screen()
    assert not menu.add_rule_dialog(reader=scripted([""]), printer=screen)
    assert knowledge.load_rules() == []
    assert "Ничего не добавил" in screen.text


def test_remove_rule_by_number(files):
    knowledge.add_rule("первое")
    knowledge.add_rule("второе")
    screen = Screen()
    assert menu.remove_rule_dialog(reader=scripted(["1"]), printer=screen)
    assert knowledge.load_rules() == ["второе"]
    assert "Удалил: первое" in screen.text


def test_remove_rule_with_garbage_number(files):
    knowledge.add_rule("первое")
    screen = Screen()
    assert not menu.remove_rule_dialog(reader=scripted(["десять"]), printer=screen)
    assert knowledge.load_rules() == ["первое"]
    assert "не номер" in screen.text


def test_lessons_are_shown_with_problem_and_fix(files):
    knowledge.add_lesson(problem="заготовка не определена",
                         fix="FORM BLOCK + BLOCK ACCEPT",
                         task="черновая", when="2026-01-01 00:00")
    screen = Screen()
    menu.show_lessons(printer=screen)
    assert "заготовка не определена" in screen.text
    assert "FORM BLOCK + BLOCK ACCEPT" in screen.text


def test_manual_lesson_dialog_asks_three_questions(files):
    screen = Screen()
    assert menu.add_lesson_dialog(
        reader=scripted(["проверки траекторий", "нет державки",
                         "поставил державку в PowerMill"]),
        printer=screen)
    lesson = knowledge.load_lessons()[0]
    assert lesson.source == "вручную"
    assert lesson.fix == "поставил державку в PowerMill"


def test_manual_lesson_without_problem_is_not_written(files):
    screen = Screen()
    assert not menu.add_lesson_dialog(reader=scripted(["дело", "", ""]),
                                      printer=screen)
    assert knowledge.load_lessons() == []


def test_shows_how_it_works(files):
    text = menu.help_text()
    assert "ОБЛАКО ЗАПРЕЩЕНО" in text
    assert "не переучивается" in text


def test_command_line_add_and_show(files, capsys):
    assert menu.main(["--add", "правило из командной строки"]) == 0
    assert knowledge.load_rules() == ["правило из командной строки"]
    assert menu.main(["--show"]) == 0
    out = capsys.readouterr().out
    assert "правило из командной строки" in out
    assert "Правил: 1" in out


def test_command_line_refuses_empty_rule(files, capsys):
    assert menu.main(["--add", "   "]) == 1
    assert knowledge.load_rules() == []
