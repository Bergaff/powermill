"""Тесты разведки: чем можно подключиться к PowerMill.

Модуль ничего не меняет на машине — он только читает сведения. Здесь
проверяем логику заключений (маршруты A/B/C) на придуманных данных и
запись макроса-разведчика.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src import power_mill_link as link


# --------------------------------------------------------------------------
# Заключения по маршрутам
# --------------------------------------------------------------------------
def test_route_a_available_when_powermill_installed():
    data = {"install_dirs": [Path("E:/powermill 2026/PowerMill 2026")],
            "executables": ["E:/powermill 2026/PowerMill 2026/PowerMill.exe"]}
    routes = {r["code"]: r for r in link.verdict(data)}
    assert routes["A"]["available"] is True
    assert "готово" in routes["A"]["note"]


def test_route_a_unavailable_without_powermill():
    routes = {r["code"]: r for r in link.verdict({})}
    assert routes["A"]["available"] is False
    assert "не найден" in routes["A"]["note"]


def test_route_b_requires_api_assemblies_and_python_bridge():
    data = {
        "install_dirs": [Path("E:/pm")],
        "assemblies": {"Autodesk.ProductInterface.PowerMILL.dll": ["E:/pm/x.dll"]},
        "bridges": {"pywin32 (COM)": False, "pythonnet (.NET)": False},
    }
    route = {r["code"]: r for r in link.verdict(data)}["B"]
    assert route["available"] is False
    assert "моста Python" in route["note"]   # объясняем, чего не хватает
    assert "пункт 27" in route["action"]     # и что для этого сделать


def test_route_b_with_com_registration_points_to_bridge_install():
    """Реальный случай пользователя: COM есть, сборки API есть, моста нет."""
    data = {
        "install_dirs": [Path("E:/powermill 2026/PowerMill 2026")],
        "assemblies": {"Delcam.ProductInterface.PowerMILL.dll":
                       ["C:/Program Files/Autodesk/PowerMill Project Server 2026/x.dll"]},
        "progids": ["PowerMill.Application", "PowerMILL.Application"],
        "bridges": {"pywin32 (COM)": False, "pythonnet (.NET)": False},
    }
    route = {r["code"]: r for r in link.verdict(data)}["B"]
    assert route["available"] is False
    assert "COM-регистрация" in route["note"]
    assert "пункт 27" in route["action"]


def test_route_c_mentions_installed_plugins():
    data = {"install_dirs": [Path("E:/pm"),
                             Path("C:/Program Files/Autodesk/Autodesk PowerMill Robot Plugin 2026")],
            "assemblies": {}}
    route = {r["code"]: r for r in link.verdict(data)}["C"]
    assert route["available"] is False
    assert "опереться" in route["note"]
    assert "пункт 25" in route["action"]


def test_route_b_available_when_everything_present():
    data = {
        "install_dirs": [Path("E:/pm")],
        "assemblies": {"Autodesk.ProductInterface.PowerMILL.dll": ["E:/pm/x.dll"]},
        "bridges": {"pywin32 (COM)": True},
    }
    route = {r["code"]: r for r in link.verdict(data)}["B"]
    assert route["available"] is True
    assert "реальном времени" in route["note"]


def test_route_b_can_work_through_com_only():
    data = {"install_dirs": [Path("E:/pm")],
            "progids": ["PowerMill.Application"],
            "bridges": {"pywin32 (COM)": True}}
    assert {r["code"]: r for r in link.verdict(data)}["B"]["available"] is True


def test_route_c_always_later():
    data = {"install_dirs": [Path("E:/pm")],
            "assemblies": {"Autodesk.WPFControls.ProductControls.PowerMILL.dll": ["x"]}}
    route = {r["code"]: r for r in link.verdict(data)}["C"]
    assert route["available"] is False
    assert "WPF" in route["note"]


# --------------------------------------------------------------------------
# Отчёт
# --------------------------------------------------------------------------
def test_report_marks_routes():
    data = {"install_dirs": [Path("E:/pm")], "executables": ["E:/pm/PowerMill.exe"],
            "assemblies": {}, "bridges": {}, "running": False}
    text = link.format_report(data)
    assert "РАЗВЕДКА" in text
    assert "[МОЖНО]" in text
    assert "[НЕЛЬЗЯ]" in text or "[ПОЗЖЕ]" in text
    assert "A. PML-макросы" in text


def test_report_mentions_running_state():
    text = link.format_report({"install_dirs": [], "running": True})
    assert "запущен" in text


# --------------------------------------------------------------------------
# Макрос-разведчик
# --------------------------------------------------------------------------
def test_probe_macro_is_valid_pml_looking():
    macro = link.PROBE_MACRO
    assert macro.count("FOREACH") == macro.count("}") - 0 or "FOREACH" in macro
    assert macro.count("{") == macro.count("}")      # скобки сбалансированы
    assert "POWERMILL AI PROBE START" in macro
    assert 'FOLDER("Toolpath")' in macro
    # никаких догадок про переменные версии — только надёжные конструкции
    assert "${version}" not in macro


def test_write_probe_macro(tmp_path):
    path = link.write_probe_macro(tmp_path)
    assert path.name == "PM_PROBE.mac"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "PROBE END" in text
    # путь к снимку берётся из переданной папки, а не из константы
    assert "pm_project.txt" in text
    assert str(tmp_path) in text


def test_probe_macro_writes_file_not_only_console():
    """Макрос сам пишет файл — иначе кажется, что он «ничего не делает»."""
    text = link.probe_macro("E:/powermill-ai/output/pm_project.txt")
    assert "FILE OPEN $outfile FOR WRITE AS out" in text
    assert "FILE WRITE" in text
    assert "FILE CLOSE out" in text
    assert "MESSAGE INFO" in text                  # видимое окно в конце
    assert 'FILE WRITE "MODELS:" TO out' in text
    assert "STOCK MODELS:" in text and "PATTERNS:" in text
    assert "E:\\powermill-ai\\output\\pm_project.txt" in text


def test_probe_macro_passes_our_pml_vocab():
    from src import pml_vocab

    vocab = {"entities": ["model", "boundary", "tool", "toolpath", "workplane",
                          "ncprogram", "stockmodel", "pattern"], "parameters": []}
    report = pml_vocab.validate(link.probe_macro("output/pm_project.txt"), vocab)
    assert report["ok"], pml_vocab.format_check(report)


def test_probe_macro_sections_cover_project():
    for header, folder in link.PROBE_SECTIONS:
        assert header and folder
        assert f'FOLDER("{folder}")' in link.probe_macro("x/pm_project.txt")


# --------------------------------------------------------------------------
# Разведка на текущей машине не должна падать
# --------------------------------------------------------------------------
def test_collect_does_not_crash():
    data = link.collect()
    assert "install_dirs" in data
    assert isinstance(data["bridges"], dict)
    assert isinstance(link.verdict(data), list)


def test_find_api_assemblies_ignores_other_files(tmp_path):
    (tmp_path / "PowerMill.exe").write_text("x", encoding="utf-8")
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "Autodesk.ProductInterface.PowerMILL.dll").write_text("x", encoding="utf-8")
    found = link.find_api_assemblies([tmp_path])
    assert "Autodesk.ProductInterface.PowerMILL.dll" in found
    assert len(found) == 1
