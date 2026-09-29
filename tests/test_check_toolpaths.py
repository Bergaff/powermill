"""
Тесты пункта 35 (scripts/check_toolpaths.py) — того самого места, где живой
PowerMill сказал «не заданы ни хвостовик ни патрон».

Проверяем поведение пункта, а не PowerMill: он должен
* задать условную державку и сказать об этом честно;
* НЕ включать проверку столкновений в макрос, если PowerMill считать её не может
  (иначе макрос останавливается и отчёта не будет);
* в любом случае проверить зарезы и написать, что именно не проверено.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import check_toolpaths
from src import pm_check, pm_holder


class FakeSession:
    """Живой PowerMill «понарошку»: отвечает на команды и ругается по заказу."""

    version = "2026000"

    def __init__(self, refusal: str = ""):
        self.commands: list[str] = []
        self.refusal = refusal

    def section_names(self, section: str):
        return {
            "toolpaths": ["Chernovaya_D16"],
            "tools": ["Chernovaya_D16"],
            "ncprograms": [],
            "models": ["Деталь1"],
        }.get(section, [])

    def execute(self, command: str):
        self.commands.append(command)
        if self.refusal and command == "EDIT COLLISION APPLY":
            return True, ("DoCommand('EDIT COLLISION APPLY') -> OK | ответ: "
                          + self.refusal)
        return True, "DoCommand(...) -> OK"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(pm_holder, "SPEC_FILE", tmp_path / "holder_defaults.json")
    macro_file = tmp_path / "pm_check.mac"
    original_write = pm_check.write_macro

    def write_here(plan, path=None):
        original_write(plan, path=macro_file)
        return macro_file

    monkeypatch.setattr(pm_check, "MACRO_FILE", macro_file)
    monkeypatch.setattr(pm_check, "write_macro", write_here)
    monkeypatch.setattr(pm_check, "trace_files",
                        lambda: [tmp_path / f"pm_check_trace_{n}.txt" for n in (1, 2, 3)])
    monkeypatch.setattr(check_toolpaths, "REPORT_FILE", tmp_path / "pm_check_report.txt")
    monkeypatch.setattr(check_toolpaths, "wait_for_result", lambda *a, **k: True)
    monkeypatch.setattr(pm_check, "last_result",
                        lambda *a, **k: ([("exists", "ok", "Chernovaya_D16"),
                                          ("gouge", "ok", "Chernovaya_D16: зарезы проверены")], ""))
    return tmp_path


def scripted(monkeypatch, answers: list[str]):
    queue = list(answers)

    def fake_read_line(_prompt: str = ""):
        return queue.pop(0) if queue else ""

    monkeypatch.setattr(check_toolpaths, "read_line", fake_read_line)


# траектории, фреза, зазор державки, зазор хвостовика, державка, диаметр, «запускать?»
ENTER = ["", "", "", "", "", "", "да"]


def test_holder_is_set_and_collisions_are_dropped_when_power_mill_refuses(env, monkeypatch):
    session = FakeSession(refusal="не заданы ни хвостовик ни патрон")
    monkeypatch.setattr(check_toolpaths.pm_com, "connect", lambda: (session, "живой PowerMill"))
    scripted(monkeypatch, ENTER)

    assert check_toolpaths.main() == 0

    sent = "\n".join(session.commands)
    assert "SHANK_COMPONENT ADD" in sent and "HOLDER_COMPONENT ADD" in sent

    macro = pm_check.MACRO_FILE.read_text(encoding="cp1251")
    assert "EDIT COLLISION TYPE COLLISION" not in macro     # иначе макрос умрёт
    assert "EDIT COLLISION TYPE GOUGE" in macro             # зарезы проверяем

    report = check_toolpaths.REPORT_FILE.read_text(encoding="utf-8")
    assert "столкновения не проверялись" in report
    assert "не заданы ни хвостовик ни патрон" in report


def test_collisions_stay_when_power_mill_can_check_them(env, monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(check_toolpaths.pm_com, "connect", lambda: (session, "живой PowerMill"))
    scripted(monkeypatch, ENTER)

    assert check_toolpaths.main() == 0
    macro = pm_check.MACRO_FILE.read_text(encoding="cp1251")
    assert "EDIT COLLISION TYPE COLLISION" in macro

    report = check_toolpaths.REPORT_FILE.read_text(encoding="utf-8")
    assert "УСЛОВНОЙ державкой" in report            # про подмену сказано прямо


def test_saying_no_to_the_holder_keeps_the_tool_untouched(env, monkeypatch):
    session = FakeSession(refusal="не заданы ни хвостовик ни патрон")
    monkeypatch.setattr(check_toolpaths.pm_com, "connect", lambda: (session, "живой PowerMill"))
    answers = list(ENTER)
    answers[4] = "нет"                                # державку не задавать
    scripted(monkeypatch, answers)

    assert check_toolpaths.main() == 0
    assert not any("COMPONENT" in command for command in session.commands)
    # PowerMill всё равно не может — значит столкновений в макросе нет, и это сказано
    assert "EDIT COLLISION TYPE COLLISION" not in pm_check.MACRO_FILE.read_text(encoding="cp1251")
    report = check_toolpaths.REPORT_FILE.read_text(encoding="utf-8")
    assert "столкновения не проверялись" in report


def test_no_live_power_mill_means_nothing_is_changed(env, monkeypatch):
    monkeypatch.setattr(check_toolpaths.pm_com, "connect",
                        lambda: (None, "pywin32 не установлен"))
    scripted(monkeypatch, ENTER)

    assert check_toolpaths.main() == 1
    assert not pm_check.MACRO_FILE.exists()
    assert not check_toolpaths.REPORT_FILE.exists()
