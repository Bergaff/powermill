"""
Тесты мастера пункта 33 (scripts/probe_tool.py).

Проверяем то, за что технолог отвечает головой: без живого PowerMill пункт
честно отказывается работать, а с живым — показывает команды до выполнения,
спрашивает подтверждение и пишет отчёт.
"""
from __future__ import annotations

import pytest

from scripts import probe_tool
from src import pm_tool


class FakeSession:
    """Подставной живой PowerMill: слово END_MILL создаёт фрезу."""

    version = "2026000"

    def __init__(self, tools=()):
        self.tools = list(tools)
        self.commands: list[str] = []

    def section_names(self, section: str):
        if section == "models":
            return ["Деталь1"]
        assert section == "tools"
        return list(self.tools)

    def execute(self, command: str):
        self.commands.append(command)
        if command.startswith("CREATE TOOL ; "):
            word = command.split(";", 1)[1].strip()
            if word == "END_MILL":
                self.tools.append("Tool1")
                return True, "DoCommand(...) -> OK"
            return False, "недопустимый элемент или команда"
        if command.startswith("RENAME Tool"):
            self.tools[-1] = command.split(";", 1)[1].strip().strip("'")
        return True, "OK"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Пункт 33 с отчётом и памятью слова во временной папке."""
    monkeypatch.setattr(pm_tool, "WORD_FILE", tmp_path / "pm_tool_word.txt")
    monkeypatch.setattr(probe_tool, "REPORT_FILE", tmp_path / "pm_tool_report.txt")
    return tmp_path


def scripted(monkeypatch, answers: list[str]):
    """Подставляет ответы технолога вместо ввода с клавиатуры."""
    queue = list(answers)

    def fake_read_line(_prompt: str = ""):
        return queue.pop(0) if queue else ""

    monkeypatch.setattr(probe_tool, "read_line", fake_read_line)


def test_no_live_powermill_refuses_to_work(env, monkeypatch):
    monkeypatch.setattr(probe_tool.pm_com, "connect",
                        lambda: (None, "pywin32 не установлен"))
    assert probe_tool.main() == 1
    assert not probe_tool.REPORT_FILE.exists()


def test_live_powermill_state_read(env, monkeypatch):
    session = FakeSession(tools=["Staraya_Freza"])
    monkeypatch.setattr(probe_tool.pm_com, "connect", lambda: (session, "ok"))

    models, tools, source = probe_tool.live_state()
    assert models == ["Деталь1"]
    assert tools == ["Staraya_Freza"]
    assert "живой" in source and "2026000" in source


def test_wizard_creates_tool_and_writes_report(env, monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(probe_tool.pm_com, "connect", lambda: (session, "ok"))
    # имя (Enter = D16_Freza), диаметр (Enter = 16), подтверждение «да»
    scripted(monkeypatch, ["", "", "да"])

    assert probe_tool.main() == 0

    assert session.tools == ["D16_Freza"]
    text = probe_tool.REPORT_FILE.read_text(encoding="utf-8")
    assert "CREATE TOOL ; END_MILL" in text
    assert "D16_Freza" in text
    assert pm_tool.saved_word() == "END_MILL"


def test_wizard_does_nothing_without_confirmation(env, monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(probe_tool.pm_com, "connect", lambda: (session, "ok"))
    scripted(monkeypatch, ["", "", "нет"])

    assert probe_tool.main() == 0
    assert session.commands == []                    # проект не тронут
    assert not probe_tool.REPORT_FILE.exists()


def test_wizard_back_returns_to_menu(env, monkeypatch):
    """«назад» на первом шаге — выход в меню, проект не меняется."""
    session = FakeSession()
    monkeypatch.setattr(probe_tool.pm_com, "connect", lambda: (session, "ok"))
    scripted(monkeypatch, ["назад"])

    assert probe_tool.main() == 0
    assert session.commands == []


def test_wizard_uses_existing_tool(env, monkeypatch):
    session = FakeSession(tools=["D16_Freza"])
    monkeypatch.setattr(probe_tool.pm_com, "connect", lambda: (session, "ok"))
    scripted(monkeypatch, ["D16_Freza", "16", "да"])

    assert probe_tool.main() == 0
    assert session.tools == ["D16_Freza"]
    assert not any(command.startswith("CREATE TOOL") for command in session.commands)


def test_ask_yes_no_parses_answers(monkeypatch):
    for text, expected in (("да", True), ("", False), ("нет", False),
                           ("yes", True), ("д", True), ("1", True), ("0", False)):
        scripted(monkeypatch, [text])
        assert probe_tool.ask_yes_no("?") is expected, text


def test_ask_yes_no_repeats_on_garbage(monkeypatch):
    scripted(monkeypatch, ["абракадабра", "да"])
    assert probe_tool.ask_yes_no("?") is True


def test_ask_yes_no_returns_none_on_exit(monkeypatch):
    scripted(monkeypatch, [])                        # read_line вернёт ""
    assert probe_tool.ask_yes_no("?") is False
    monkeypatch.setattr(probe_tool, "read_line", lambda _p="": None)
    assert probe_tool.ask_yes_no("?") is None


def test_bad_diameter_falls_back_to_16(env, monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(probe_tool.pm_com, "connect", lambda: (session, "ok"))
    scripted(monkeypatch, ["", "шестнадцать", "да"])

    assert probe_tool.main() == 0
    text = probe_tool.REPORT_FILE.read_text(encoding="utf-8")
    assert "DIAMETER 16" in text
