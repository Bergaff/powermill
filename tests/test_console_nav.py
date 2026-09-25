"""Тесты навигации в консоли: слова-команды и пошаговый мастер."""
from __future__ import annotations

import pytest

from src.console import Wizard, classify


# --------------------------------------------------------------------------
# Слова-команды
# --------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["назад", "Назад", " back ", "-", "<", "н", "B"])
def test_back_words(text):
    assert classify(text) == "back"


@pytest.mark.parametrize("text", ["меню", "МЕНЮ", "menu", "m", "выход", "exit", "q"])
def test_menu_words(text):
    assert classify(text) == "menu"


@pytest.mark.parametrize("text", ["?", "help", "справка", "помощь"])
def test_help_words(text):
    assert classify(text) == "help"


@pytest.mark.parametrize("text", ["", "  ", "далее", "next", "ок"])
def test_skip_words(text):
    assert classify(text) == "skip"


def test_regular_input():
    assert classify("Сталь 40Х") == "input"
    assert classify("фреза D16") == "input"


# --------------------------------------------------------------------------
# Мастер
# --------------------------------------------------------------------------
STEPS = [
    ("Материал", "сталь/алюминий", "Сталь 40Х"),
    ("Инструмент", "фреза D16", "фреза D16 z4"),
    ("Операция", "черновая/чистовая", "черновая"),
]


def test_wizard_collects_answers_in_order():
    w = Wizard(STEPS)
    assert w.submit("Д16Т") == "next"
    assert w.submit("сферическая D8") == "next"
    assert w.submit("чистовая") == "done"
    assert w.query() == "Д16Т, сферическая D8, чистовая"


def test_wizard_back_returns_to_previous_step():
    w = Wizard(STEPS)
    w.submit("Д16Т")
    w.submit("сферическая D8")
    assert w.index == 2
    assert w.submit("назад") == "back"
    assert w.index == 1
    assert w.current()[0] == "Инструмент"


def test_wizard_back_keeps_previous_answer_as_default():
    w = Wizard(STEPS)
    w.submit("Сталь 45")
    w.submit("назад")
    assert w.current()[2] == "Сталь 45"      # значение по умолчанию — прошлый ответ
    w.submit("")                             # Enter — оставить
    assert w.answers[0] == "Сталь 45"
    assert w.index == 1


def test_wizard_back_from_first_step_means_menu():
    w = Wizard(STEPS)
    assert w.submit("назад") == "menu"


def test_wizard_menu_and_help_do_not_change_state():
    w = Wizard(STEPS)
    w.submit("Д16Т")
    assert w.submit("меню") == "menu"
    assert w.index == 1 and w.answers[0] == "Д16Т"
    assert w.submit("?") == "help"
    assert w.index == 1


def test_wizard_skip_uses_default():
    w = Wizard(STEPS)
    assert w.submit("") == "next"
    assert w.answers[0] == "Сталь 40Х"


def test_wizard_defaults_from_previous_run():
    w = Wizard(STEPS, answers=["Сталь 45", "торцевая D63", "получистовая"])
    assert w.current()[2] == "Сталь 45"
    w.submit("")                              # Enter — оставить прежнее
    w.submit("")
    w.submit("")
    assert w.query() == "Сталь 45, торцевая D63, получистовая"


def test_wizard_restart_keeps_answers():
    w = Wizard(STEPS)
    w.submit("Сталь 45")
    w.submit("фреза D10")
    w.submit("чистовая")
    w.restart()
    assert w.index == 0
    assert w.answers[0] == "Сталь 45"
    assert w.query() == "Сталь 45, фреза D10, чистовая"


def test_wizard_query_fallback():
    assert Wizard(STEPS).query("по умолчанию") == "по умолчанию"
