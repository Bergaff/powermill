"""
Тесты пункта 33 — создание фрезы в живом PowerMill и поиск рабочего слова.

Живой PowerMill здесь не нужен: подставляем подставной объект-сессию, который
ведёт список инструментов и знает, какое слово у него «работает». Так проверяем
и порядок проб, и отчёт, и поведение, когда слово не подошло.
"""
from __future__ import annotations

import pytest

from src import pm_com, pm_operation, pm_tool


class FakeSession:
    """Подставной живой PowerMill: создаёт фрезу только «правильным» словом."""

    def __init__(self, valid=("END_MILL",), tools=(), fail_section=False):
        self.valid = set(valid)
        self.tools = list(tools)
        self.commands: list[str] = []
        self.fail_section = fail_section

    def section_names(self, section: str):
        assert section == "tools"
        if self.fail_section:
            raise RuntimeError("PowerMill не отвечает")
        return list(self.tools)

    def execute(self, command: str):
        self.commands.append(command)
        if command.startswith("CREATE TOOL ; "):
            word = command.split(";", 1)[1].strip()
            if word in self.valid:
                self.tools.append(f"Tool{len(self.tools) + 1}")
                return True, "DoCommand(...) -> OK"
            return False, "DoCommand: недопустимый элемент или команда"
        if command.startswith("RENAME Tool"):
            name = command.split(";", 1)[1].strip().strip("'")
            if self.tools:
                self.tools[-1] = name
            return True, "OK"
        return True, "OK"


@pytest.fixture(autouse=True)
def word_file(tmp_path, monkeypatch):
    """Слово-память (output\\pm_tool_word.txt) — во временном файле."""
    monkeypatch.setattr(pm_tool, "WORD_FILE", tmp_path / "pm_tool_word.txt")
    return tmp_path / "pm_tool_word.txt"


# --------------------------------------------------------------------------
# поиск рабочего слова
# --------------------------------------------------------------------------
def test_create_tool_finds_working_word():
    session = FakeSession(valid=("ENDMILL",))
    report = pm_tool.create_flat_tool(session, name="D16_Freza", diameter=16)

    assert report.ok is True
    assert report.word == "ENDMILL"
    assert "D16_Freza" in report.after
    assert session.tools == ["D16_Freza"]
    assert "EDIT TOOL ; DIAMETER 16" in session.commands
    assert "EDIT TOOL ; NUMBER COMMANDFROMUI 1" in session.commands
    assert "RENAME Tool ; 'D16_Freza'" in session.commands


def test_create_tool_tries_words_in_order_and_reports_failures():
    session = FakeSession(valid=("END MILL",))
    report = pm_tool.create_flat_tool(session, words=("END_MILL", "ENDMILL", "END MILL"))

    tried = [step.command for step in report.steps if step.command.startswith("CREATE TOOL")]
    assert tried == ["CREATE TOOL ; END_MILL", "CREATE TOOL ; ENDMILL",
                     "CREATE TOOL ; END MILL"]
    assert [step.ok for step in report.steps if step.command.startswith("CREATE TOOL")] == \
        [False, False, True]
    assert report.word == "END MILL"


def test_remembered_word_goes_first():
    pm_tool.remember_word("endmill")
    assert pm_tool.saved_word() == "ENDMILL"
    assert pm_tool.word_order() [0] == "ENDMILL"
    assert pm_tool.word_order() == ["ENDMILL", "END_MILL", "END MILL"]


def test_saved_word_is_used_by_macro_first(tmp_path, monkeypatch):
    """Пункт 31 подставляет проверенное слово первым — макрос не падает зря."""
    monkeypatch.setattr(pm_tool, "WORD_FILE", tmp_path / "pm_tool_word.txt")
    pm_tool.remember_word("ENDMILL")

    words = pm_operation.tool_words()
    assert words[0] == "ENDMILL"

    code = pm_operation.build_macro(pm_operation.OperationPlan(
        toolpath_name="Черновая", tool_name="D16", tool_diameter=16))
    first = code.index("CREATE TOOL ; ENDMILL")
    second = code.index("CREATE TOOL ; END_MILL")
    assert first < second


def test_dialogs_are_restored_after_probe():
    session = FakeSession(valid=("END_MILL",))
    pm_tool.create_flat_tool(session)
    assert session.commands.index("DIALOGS MESSAGE OFF") < \
        session.commands.index("CREATE TOOL ; END_MILL")
    assert "DIALOGS ERROR ON" in session.commands
    assert "DIALOGS MESSAGE ON" in session.commands


# --------------------------------------------------------------------------
# случаи, когда создавать не нужно или нельзя
# --------------------------------------------------------------------------
def test_existing_tool_is_left_alone():
    session = FakeSession(tools=["D16_Freza"])
    report = pm_tool.create_flat_tool(session, name="D16_Freza")

    assert report.ok is True
    assert "уже есть" in report.message
    assert not any(command.startswith("CREATE TOOL") for command in session.commands)


def test_no_word_worked_gives_honest_report():
    session = FakeSession(valid=())
    report = pm_tool.create_flat_tool(session)

    assert report.ok is False
    assert "ни одно из слов" in report.message
    assert session.tools == []
    assert pm_tool.saved_word() == ""


def test_unreadable_tool_list_is_reported():
    session = FakeSession(fail_section=True)
    report = pm_tool.create_flat_tool(session)
    assert report.ok is False
    assert "не удалось прочитать список инструментов" in report.message


def test_report_format_contains_commands_and_result():
    session = FakeSession(valid=("END_MILL",))
    text = pm_tool.create_flat_tool(session, name="D16_Freza").format()
    assert "CREATE TOOL ; END_MILL" in text
    assert "D16_Freza" in text
    assert "Слово создания фрезы: END_MILL" in text


# --------------------------------------------------------------------------
# живой COM: ответ PowerMill попадает в отчёт
# --------------------------------------------------------------------------
class FakeApp:
    """Минимальное «приложение» PowerMill для проверки execute()."""

    def __init__(self, answer="POWERMILL AI TEST OK"):
        self.answer = answer
        self.commands: list[str] = []

    def DoCommand(self, command):
        self.commands.append(command)
        return self.answer

    class _Version:
        Version = "2026000"

    Version = _Version()


def test_execute_keeps_powermill_answer():
    session = pm_com.LiveSession(FakeApp())
    ok, note = session.execute("PRINT \"привет\"")
    assert ok is True
    assert "POWERMILL AI TEST OK" in note


def test_execute_without_answer_still_works():
    session = pm_com.LiveSession(FakeApp(answer=None))
    ok, note = session.execute("UNDRAW TOOLPATH ALL")
    assert ok is True
    assert "OK" in note


def test_execute_collects_error_text():
    class Broken:
        def DoCommand(self, command):
            raise RuntimeError("недопустимый элемент или команда")

        def Execute(self, command):
            return ""

    ok, note = pm_com.LiveSession(Broken()).execute("CREATE TOOL ; ЕРУНДА")
    assert ok is True                      # Execute() сработал
    assert "DoCommand" in note             # и видно, что первый способ ругнулся
