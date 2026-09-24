"""Проверка «запущена ли PowerMill» — по опыту живого PowerMill 2026.

В отчёте пользователя было «PowerMill сейчас: не запущен», хотя проект
читался живьём: процесс PowerMill называется `pmill.exe`, и проверка по
подстроке «powermill» его не видела. Поэтому имён теперь два, плюс запасной
способ — спросить COM-объект.
"""
from __future__ import annotations

import sys
import types

from src import power_mill_link as link


class _FakeProc:
    def __init__(self, name: str):
        self.info = {"name": name}


def _fake_psutil(monkeypatch, names: list[str]) -> None:
    module = types.ModuleType("psutil")
    module.process_iter = lambda _attrs=None: [_FakeProc(n) for n in names]
    monkeypatch.setitem(sys.modules, "psutil", module)


def test_detects_pmill_exe(monkeypatch):
    """Сама PowerMill — pmill.exe; раньше это считалось «не запущена»."""
    _fake_psutil(monkeypatch, ["pmill.exe", "explorer.exe"])
    assert link.powermill_running() is True


def test_detects_powermill_exe(monkeypatch):
    _fake_psutil(monkeypatch, ["PowerMill.exe"])
    assert link.powermill_running() is True


def test_other_processes_are_not_powermill(monkeypatch):
    _fake_psutil(monkeypatch, ["chrome.exe", "explorer.exe"])
    monkeypatch.setattr(link, "com_object_alive", lambda: False)
    assert link.powermill_running() is False


def test_com_fallback_used_when_no_process(monkeypatch):
    """Процессов не видно, но COM-объект отвечает — значит PowerMill работает."""
    _fake_psutil(monkeypatch, ["explorer.exe"])
    monkeypatch.setattr(link, "com_object_alive", lambda: True)
    assert link.powermill_running() is True


def test_com_object_alive_outside_windows(monkeypatch):
    monkeypatch.setattr(link.os, "name", "posix")
    assert link.com_object_alive() is None


def test_progids_cover_real_registration():
    """В реестре пользователя есть PowerMill.Application — он должен быть первым."""
    assert link.KNOWN_PROGIDS[0] == "PowerMill.Application"
    assert "PowerMILL.Application" in link.KNOWN_PROGIDS
