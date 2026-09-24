"""Тесты пункта 29 — просмотр отчётов (чтобы не копировать с экрана)."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import show_reports


@pytest.fixture
def fake_output(tmp_path, monkeypatch):
    monkeypatch.setattr(show_reports, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(show_reports, "DATA_ROOT", tmp_path.parent)
    return tmp_path


def test_collect_files_finds_known_reports(fake_output):
    (fake_output / "pm_api_probe.txt").write_text("разведка", encoding="utf-8")
    (fake_output / "pm_macros_report.txt").write_text("макросы", encoding="utf-8")
    (fake_output / "logs").mkdir()
    (fake_output / "logs" / "run.log").write_text("лог", encoding="utf-8")

    names = [p.name for p in show_reports.collect_files()]
    assert "pm_api_probe.txt" in names
    assert "pm_macros_report.txt" in names
    assert "run.log" in names


def test_collect_files_ignores_api_key(fake_output):
    (fake_output / "api_key.json").write_text("{}", encoding="utf-8")
    (fake_output / "pm_link_report.txt").write_text("связь", encoding="utf-8")

    names = [p.name for p in show_reports.collect_files()]
    assert "api_key.json" not in names          # ключ не показываем и не открываем
    assert "pm_link_report.txt" in names


def test_collect_files_on_empty_folder(fake_output):
    assert show_reports.collect_files() == []


def test_describe_mentions_human_title(fake_output):
    path = fake_output / "pm_api_probe.txt"
    path.write_text("x", encoding="utf-8")
    text = show_reports.describe(path)
    assert "pm_api_probe.txt" in text
    assert "пункт 27" in text


def test_main_handles_empty_folder(fake_output, capsys):
    assert show_reports.main() == 0
    assert "Отчётов пока нет" in capsys.readouterr().out


def test_menu_offers_back_and_opens_by_number(fake_output, monkeypatch, capsys):
    (fake_output / "pm_api_probe.txt").write_text("x", encoding="utf-8")
    opened: list[Path] = []
    monkeypatch.setattr(show_reports, "open_in_notepad",
                        lambda path: opened.append(path) or True)

    answers = iter(["1", "0"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    assert show_reports.main() == 0
    assert opened and opened[0].name == "pm_api_probe.txt"


def test_wrong_number_does_not_open_anything(fake_output, monkeypatch, capsys):
    (fake_output / "pm_api_probe.txt").write_text("x", encoding="utf-8")
    opened: list[Path] = []
    monkeypatch.setattr(show_reports, "open_in_notepad",
                        lambda path: opened.append(path) or True)

    answers = iter(["99", "назад"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    show_reports.main()
    assert opened == []
    assert "Нет такого номера" in capsys.readouterr().out
