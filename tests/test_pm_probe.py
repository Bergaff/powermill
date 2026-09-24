"""Тесты разведки API PowerMill и установки моста (шаги 2.1 / пункт 27).

Настоящего PowerMill в песочнице нет, поэтому проверяем:
* разведку на «поддельном» COM-объекте (все вопросы должны получить ответы,
  ничего не должно падать даже при «сломанных» свойствах);
* понятные сообщения, когда мостов нет;
* установщик моста: определение интерпретатора, разбор ошибок pip.
"""
from __future__ import annotations

import pytest

from src import pm_probe


# --------------------------------------------------------------------------
# Поддельный COM-объект PowerMill
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
        self.Models = FakeCollection(["Blok"])
        self.Toolpaths = FakeCollection(["Rough_D16", "Finish_D8"])
        self.Tools = FakeCollection(["D16_R3"])
        self.Boundaries = FakeCollection([])
        self.Broken = property(lambda self: (_ for _ in ()).throw(RuntimeError("нет доступа")))

    def DoCommand(self, command: str):
        self.command = command
        return 0


class FakePowerMill:
    """Похож на COM-объект PowerMill: проект, методы команд."""

    def __init__(self):
        self.ActiveProject = FakeProject()

    def DoCommand(self, command: str):
        self.last_command = command
        return 0

    def ExecuteMacro(self, path: str):
        self.last_macro = path


def test_probe_com_object_describes_methods():
    lines = pm_probe.probe_com_object(FakePowerMill())
    text = "\n".join(lines)
    assert "Что умеет COM-объект PowerMill" in text
    assert "ActiveProject: найден" in text
    assert "DoCommand" in text


def test_probe_reads_collections_with_counts():
    lines = pm_probe.probe_com_object(FakePowerMill())
    text = "\n".join(lines)
    assert "Models: доступно, Count=1" in text
    assert "Toolpaths: доступно, Count=2" in text
    assert "Boundaries: доступно, Count=0" in text


def test_probe_notes_missing_project():
    class Empty:
        ActiveProject = None
        Project = None

    lines = pm_probe.probe_com_object(Empty())
    text = "\n".join(lines)
    assert "Проект не найден" in text
    assert "PowerMill не запущен" in text


def test_probe_survives_broken_attribute():
    """Свойство, которое бросает исключение, не должно ломать разведку."""

    class Broken:
        @property
        def ActiveProject(self):
            raise RuntimeError("COM-ошибка")

    lines = pm_probe.probe_com_object(Broken())
    text = "\n".join(lines)
    assert "ошибка" in text.lower()
    assert "Проект не найден" in text or "ActiveProject: ошибка" in text


def test_probe_runs_harmless_command():
    app = FakePowerMill()
    lines = pm_probe.probe_com_object(app)
    text = "\n".join(lines)
    assert "Пробное выполнение" in text
    assert app.last_command == 'PRINT "POWERMILL AI TEST OK"'
    assert "OK" in text


def test_probe_dotnet_object():
    lines = pm_probe.probe_dotnet(FakePowerMill())
    text = "\n".join(lines)
    assert "Объект .NET API" in text
    assert "Активный проект" in text
    assert "Что умеет проект" in text


# --------------------------------------------------------------------------
# Полный прогон разведки без мостов
# --------------------------------------------------------------------------
def test_run_without_bridges_explains_step_27(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pm_probe, "PROBE_FILE", tmp_path / "pm_api_probe.txt")
    monkeypatch.setattr("src.pm_live.bridges", lambda: {"pythonnet (.NET)": False,
                                                        "pywin32 (COM)": False})
    rc = pm_probe.run()
    out = capsys.readouterr().out
    assert rc == 2
    assert "пункт 27" in out
    # отчёт всё равно сохранён — его можно прислать
    assert (tmp_path / "pm_api_probe.txt").exists()


def test_run_reports_when_powermill_not_running(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pm_probe, "PROBE_FILE", tmp_path / "probe.txt")
    monkeypatch.setattr("src.pm_live.bridges", lambda: {"pywin32 (COM)": True})
    monkeypatch.setattr("src.pm_live.connect", lambda: (None, "com", "не подключилось"))
    monkeypatch.setattr("src.power_mill_link.powermill_running", lambda: False)
    rc = pm_probe.run()
    out = capsys.readouterr().out
    assert rc == 3
    assert "не запущен" in out
    assert "проект открыт" in out


def test_run_saves_report_with_connected_api(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pm_probe, "PROBE_FILE", tmp_path / "probe.txt")
    monkeypatch.setattr("src.pm_live.bridges", lambda: {"pywin32 (COM)": True})
    monkeypatch.setattr("src.pm_live.connect",
                        lambda: (FakePowerMill(), "com", "подключено через COM"))
    monkeypatch.setattr("src.power_mill_link.powermill_running", lambda: True)
    monkeypatch.setattr("src.pm_live.find_api_assembly", lambda extra=None: None)

    rc = pm_probe.run()
    text = (tmp_path / "probe.txt").read_text(encoding="utf-8")
    assert rc == 0
    assert "подключено через COM" in text
    assert "Пришли этот файл в чат" in text


# --------------------------------------------------------------------------
# Установщик моста
# --------------------------------------------------------------------------
def test_bridge_python_exe_is_current_interpreter():
    from scripts import install_bridge

    assert install_bridge.python_exe()


def test_bridge_check_import_ok():
    from scripts import install_bridge

    ok, message = install_bridge.check_import("json")
    assert ok and "ok" in message


def test_bridge_check_import_fails_cleanly():
    from scripts import install_bridge

    ok, message = install_bridge.check_import("нет_такого_модуля_12345")
    assert ok is False
    assert message


def test_bridge_packages_described_for_humans():
    from scripts import install_bridge

    titles = " ".join(purpose for _name, purpose, _mods in install_bridge.PACKAGES)
    assert "COM" in titles and ".NET" in titles


def test_bridge_checks_real_module_names():
    """Регресс: у пакета pywin32 модуль называется win32com, а не pywin32.

    Раньше проверка шла по имени пакета и врала: «импорт: ОШИБКА —
    No module named 'pywin32'» при живом-рабочем pywin32.
    """
    from scripts import install_bridge

    mapped = {name: modules for name, _purpose, modules in install_bridge.PACKAGES}
    assert "win32com.client" in mapped["pywin32"]
    assert "pywin32" not in mapped["pywin32"]
    assert "clr" in mapped["pythonnet"]


def test_bridge_check_package_reports_working_module(monkeypatch):
    from scripts import install_bridge

    def fake_check(module):
        if module == "pythoncom":
            return True, "import ok"
        return False, f"нет модуля {module}"

    monkeypatch.setattr(install_bridge, "check_import", fake_check)
    ok, message = install_bridge.check_package(("win32com.client", "pythoncom"))
    assert ok is True
    assert "pythoncom" in message


def test_bridge_check_package_lists_all_failures(monkeypatch):
    from scripts import install_bridge

    monkeypatch.setattr(install_bridge, "check_import",
                        lambda module: (False, f"нет {module}"))
    ok, message = install_bridge.check_package(("win32com.client", "pythoncom"))
    assert ok is False
    assert "win32com.client" in message and "pythoncom" in message
