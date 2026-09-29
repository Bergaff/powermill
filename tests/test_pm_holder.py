"""
Тесты державки фрезы (хвостовик и патрон).

Зачем: на живом PowerMill 2026 пункт 35 остановился с «не заданы ни хвостовик ни
патрон» — проверка столкновений без державки не работает. Здесь проверяем ровно
то, за что отвечаем: какие команды уходят в PowerMill, что размеры считаются от
диаметра фрезы, что они запоминаются и что при ошибке PowerMill мы не пишем
«всё хорошо».
"""
from __future__ import annotations

import json

import pytest

from src import pm_holder


class FakeSession:
    """Подставной PowerMill: помнит команды, умеет ругаться на выбранной."""

    def __init__(self, broken: str = ""):
        self.commands: list[str] = []
        self.broken = broken

    def execute(self, command: str):
        self.commands.append(command)
        if self.broken and self.broken in command:
            return False, "недопустимый элемент или команда"
        return True, "DoCommand(...) -> OK"


@pytest.fixture
def spec_file(tmp_path, monkeypatch):
    path = tmp_path / "holder_defaults.json"
    monkeypatch.setattr(pm_holder, "SPEC_FILE", path)
    return path


# --- размеры ---------------------------------------------------------------
def test_defaults_follow_the_tool_diameter():
    spec = pm_holder.HolderSpec.for_tool(16)
    assert spec.shank_diameter == 16
    assert spec.shank_length >= 50
    assert spec.holder_lower_diameter == 40        # типовой цанговый патрон
    assert spec.holder_upper_diameter >= 63


def test_bigger_tool_gets_bigger_holder():
    small = pm_holder.HolderSpec.for_tool(6)
    big = pm_holder.HolderSpec.for_tool(25)
    assert big.shank_diameter > small.shank_diameter
    assert big.holder_upper_diameter >= small.holder_upper_diameter


def test_zero_diameter_does_not_break():
    spec = pm_holder.HolderSpec.for_tool(0)
    assert spec.shank_diameter > 0


# --- команды ---------------------------------------------------------------
def test_lines_add_shank_and_holder_components():
    spec = pm_holder.HolderSpec.for_tool(16)
    text = "\n".join(spec.lines("D16"))
    assert "EDIT TOOL 'D16' SHANK_CLEAR" in text
    assert "EDIT TOOL 'D16' SHANK_COMPONENT ADD" in text
    assert "EDIT TOOL 'D16' SHANK_COMPONENT LOWERDIA 16" in text
    assert "EDIT TOOL 'D16' HOLDER_COMPONENT LOWERDIA 40" in text
    assert "EDIT TOOL 'D16' HOLDER_COMPONENT LENGTH 50" in text


def test_lines_can_use_a_powermill_variable():
    """В макросе надёжнее $Tool, чем литеральное имя."""
    spec = pm_holder.HolderSpec.for_tool(16)
    text = "\n".join(spec.lines("$Tool", quote=False))
    assert "EDIT TOOL $Tool SHANK_COMPONENT ADD" in text
    assert "'$Tool'" not in text


def test_quotes_in_tool_name_do_not_break_the_macro():
    text = "\n".join(pm_holder.HolderSpec().lines("Freza'1"))
    assert "EDIT TOOL 'Freza''1' SHANK_CLEAR" in text


def test_ascii_description_has_no_cp1251_problems():
    """Макросы PowerMill — CP1251: Ø и × в них не переживают запись."""
    spec = pm_holder.HolderSpec.for_tool(16)
    assert "Ø" in spec.describe()
    assert "Ø" not in spec.describe_ascii() and "×" not in spec.describe_ascii()


# --- память ---------------------------------------------------------------
def test_spec_is_remembered(spec_file):
    assert pm_holder.load_saved() is None
    spec = pm_holder.HolderSpec.for_tool(12)
    pm_holder.save_spec(spec)
    loaded = pm_holder.load_saved()
    assert loaded is not None and loaded.shank_diameter == 12


def test_broken_spec_file_is_not_a_crash(spec_file):
    spec_file.write_text("{ это не json", encoding="utf-8")
    assert pm_holder.load_saved() is None


def test_unknown_keys_in_file_are_ignored(spec_file):
    spec_file.write_text(json.dumps({"shank_diameter": 20, "мусор": 1}),
                         encoding="utf-8")
    loaded = pm_holder.load_saved()
    assert loaded is not None and loaded.shank_diameter == 20


# --- живая установка ------------------------------------------------------
def test_apply_live_sends_commands_and_reports_success():
    session = FakeSession()
    spec = pm_holder.HolderSpec.for_tool(16)
    report = pm_holder.apply_live(session, "D16", spec)

    assert report.ok
    sent = "\n".join(session.commands)
    assert "DIALOGS MESSAGE OFF" in sent and "DIALOGS ERROR OFF" in sent
    assert "SHANK_COMPONENT ADD" in sent and "HOLDER_COMPONENT ADD" in sent
    assert "DIALOGS ERROR ON" in sent                # вернули как было
    assert "условная державка" in report.format()


def test_apply_live_says_the_truth_when_a_command_fails():
    session = FakeSession(broken="SHANK_COMPONENT LENGTH")
    report = pm_holder.apply_live(session, "D16", pm_holder.HolderSpec.for_tool(16))

    assert not report.ok
    assert [step.command for step in report.failed] == [
        "EDIT TOOL 'D16' SHANK_COMPONENT LENGTH 50"]
    assert "Не все команды державки прошли" in report.format()


def test_apply_live_without_tool_name_does_nothing():
    session = FakeSession()
    report = pm_holder.apply_live(session, "", pm_holder.HolderSpec())
    assert not report.ok and session.commands == []
