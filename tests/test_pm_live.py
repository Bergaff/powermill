"""Тесты живого подключения к PowerMill (шаг 2.1).

Реального PowerMill в песочнице нет, поэтому проверяем:
* честные отчёты, когда мостов/сборок нет (без падений);
* разбор коллекций и объектов на «поддельном» API;
* что стратегии пробуются по порядку и последняя — файловая.
"""
from __future__ import annotations

import pytest

from src import pm_live


# --------------------------------------------------------------------------
# Что доступно
# --------------------------------------------------------------------------
def test_bridges_reports_both_names():
    available = pm_live.bridges()
    assert set(available) == {"pythonnet (.NET)", "pywin32 (COM)"}
    assert all(isinstance(v, bool) for v in available.values())


def test_find_api_assembly_returns_none_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr("src.power_mill_link.find_install_dirs", lambda extra=None: [])
    assert pm_live.find_api_assembly([str(tmp_path)]) is None


def test_find_api_assembly_finds_dll(tmp_path):
    folder = tmp_path / "PowerMill 2026"
    (folder / "lib").mkdir(parents=True)
    dll = folder / "lib" / "Autodesk.ProductInterface.PowerMILL.dll"
    dll.write_text("dll", encoding="utf-8")
    assert pm_live.find_api_assembly([str(tmp_path)]) == str(dll)


# --------------------------------------------------------------------------
# Подключение: в песочнице мостов нет — должны быть понятные сообщения
# --------------------------------------------------------------------------
def test_connect_com_explains_missing_pywin32():
    api, message = pm_live.connect_com(progids=("НетТакого.Класса",))
    assert api is None
    assert ("pywin32" in message) or ("COM-класс не найден" in message)


def test_connect_falls_back_to_file():
    api, strategy, message = pm_live.connect()
    if api is None:
        assert strategy == "file"
        assert "пункт 24" in message        # объясняем рабочий путь
    else:                                    # если на машине всё же есть мост
        assert strategy in {"dotnet", "com"}


def test_status_report_does_not_crash():
    text = pm_live.status_report(verbose=False)
    assert "ЖИВОЕ ПОДКЛЮЧЕНИЕ" in text
    assert "Мосты Python" in text


# --------------------------------------------------------------------------
# Разбор API на «поддельных» объектах
# --------------------------------------------------------------------------
class FakeItem:
    def __init__(self, name):
        self.Name = name


class FakeCollection:
    def __init__(self, names):
        self._names = names

    @property
    def Count(self):
        return len(self._names)

    def Item(self, index):
        return FakeItem(self._names[index])


class FakeProject:
    def __init__(self):
        self.Models = FakeCollection(["Blok", "Detal"])
        self.Toolpaths = FakeCollection(["Rough_D16", "Finish_D8"])
        self.Tools = FakeCollection(["D16_R3"])
        self.Boundaries = FakeCollection([])
        self.NCPrograms = FakeCollection([])
        self.__class__.__name__ = "FakeProject"


class FakeAutomation:
    def __init__(self):
        self.ActiveProject = FakeProject()

    def ExecuteMacro(self, path):
        self.last_macro = path


def test_iter_collection_reads_names():
    names = pm_live._iter_collection(FakeCollection(["A", "B", "C"]))
    assert names == ["A", "B", "C"]


def test_iter_collection_survives_broken_collection():
    class Broken:
        @property
        def Count(self):
            raise RuntimeError("нет доступа")

    assert pm_live._iter_collection(Broken()) == []


def test_project_objects_reads_lists():
    data, report = pm_live.project_objects(FakeAutomation())
    assert data["models"] == ["Blok", "Detal"]
    assert data["toolpaths"] == ["Rough_D16", "Finish_D8"]
    assert data["tools"] == ["D16_R3"]
    assert "models: 2" in report


def test_project_objects_without_project():
    class NoProject:
        ActiveProject = None

    data, report = pm_live.project_objects(NoProject())
    assert data == {}
    assert "открой проект" in report


def test_describe_surface_lists_names():
    text = pm_live.describe_surface(FakeAutomation(), limit=20)
    assert "ActiveProject" in text
    assert "Проект найден через ActiveProject" in text


def test_run_macro_missing_file(tmp_path):
    message = pm_live.run_macro(FakeAutomation(), str(tmp_path / "нет.mac"))
    assert "не найден" in message


def test_run_macro_uses_execute_macro(tmp_path):
    macro = tmp_path / "test.mac"
    macro.write_text("PRINT \"ok\"\n", encoding="utf-8")
    api = FakeAutomation()
    message = pm_live.run_macro(api, str(macro))
    assert "выполнен" in message
    assert api.last_macro == str(macro)
