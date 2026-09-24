"""Тесты живого подключения к PowerMill через COM (шаг 2.1).

Всё проверяется на поддельных COM-объектах: сами правила взяты из отчёта
разведки на машине технолога (PowerMill 2026) —

* проект доступен как `Project`, а `ActiveProject` такого свойства нет;
* коллекции проекта: Models, Tools, Toolpaths, Boundaries, ...
* команды выполняются методом `DoCommand`;
* присоединяться надо к ЗАПУЩЕННОМУ PowerMill (`GetActiveObject`), иначе
  `Dispatch` открывает вторую копию программы.
"""
from __future__ import annotations

import pytest

from src import pm_com


# --------------------------------------------------------------------------
# Поддельный PowerMill
# --------------------------------------------------------------------------
class FakeItem:
    def __init__(self, name: str):
        self.Name = name


class FakeCollection:
    """Коллекция как у Delcam: Count + Item(i), индексация с нуля."""

    def __init__(self, names: list[str], one_based: bool = False):
        self._items = [FakeItem(n) for n in names]
        self.Count = len(names)
        self._shift = 1 if one_based else 0

    def Item(self, index: int):
        real = index - self._shift
        if 0 <= real < len(self._items):
            return self._items[real]
        raise IndexError(index)


class EnumOnlyCollection:
    """Коллекция без Count — только перебор (проверяем фолбэк)."""

    def __init__(self, names: list[str]):
        self._items = [FakeItem(n) for n in names]

    def __iter__(self):
        return iter(self._items)


class FakeProject:
    def __init__(self, data: dict[str, list[str]]):
        self.Models = FakeCollection(data.get("models", []))
        self.Tools = FakeCollection(data.get("tools", []))
        self.Toolpaths = FakeCollection(data.get("toolpaths", []))
        self.Boundaries = FakeCollection(data.get("boundaries", []))
        self.Workplanes = FakeCollection(data.get("workplanes", []))
        self.Patterns = FakeCollection(data.get("patterns", []))
        self.StockModels = FakeCollection(data.get("stockmodels", []))
        self.NCPrograms = FakeCollection(data.get("ncprograms", []))
        self.MachineTools = FakeCollection(data.get("machinetools", []))
        self.Features = FakeCollection(data.get("features", []))
        self.Levels = FakeCollection(data.get("levels", []))
        # свойства, которого у реального PowerMill нет — проверяем, что не падаем
        self._no_active_project = True


class FakeApp:
    def __init__(self, data: dict[str, list[str]] | None = None, version: str = "2026"):
        self.Project = FakeProject(data or {})
        self.Version = version
        self.commands: list[str] = []

    def DoCommand(self, command: str):
        self.commands.append(command)
        return None

    def Execute(self, command: str):          # запасной метод
        self.commands.append("EXEC:" + command)


class NoCommandApp:
    """Приложение без методов команд — проверяем понятную ошибку."""

    def __init__(self):
        self.Project = FakeProject({})
        self.Version = "2026"


# --------------------------------------------------------------------------
# Присоединение
# --------------------------------------------------------------------------
def test_attach_does_not_start_powermill_when_not_running(monkeypatch):
    monkeypatch.setattr("src.power_mill_link.powermill_running", lambda: False)
    app, message = pm_com.attach()
    assert app is None
    assert "не запущен" in message
    assert "Запусти PowerMill" in message


def test_attach_uses_get_active_object(monkeypatch):
    """Присоединяемся к запущенному PowerMill, а не создаём новую копию."""
    calls: list[str] = []

    class FakeCom:
        @staticmethod
        def GetActiveObject(progid: str):
            calls.append(progid)
            return FakeApp()

    monkeypatch.setattr(pm_com, "_win32com", FakeCom)
    monkeypatch.setattr("src.power_mill_link.powermill_running", lambda: True)

    app, message = pm_com.attach()
    assert app is not None
    assert calls == ["PowerMill.Application"]
    assert "запущенному PowerMill" in message


def test_attach_reports_when_com_class_missing(monkeypatch):
    class FakeCom:
        @staticmethod
        def GetActiveObject(progid: str):
            raise RuntimeError("нет такого класса")

    monkeypatch.setattr(pm_com, "_win32com", FakeCom)
    monkeypatch.setattr("src.power_mill_link.powermill_running", lambda: True)

    app, message = pm_com.attach()
    assert app is None
    assert "COM-сервер" in message or "не отвечает" in message


def test_attach_without_pywin32(monkeypatch):
    monkeypatch.setattr(pm_com, "_win32com", None)
    app, message = pm_com.attach()
    assert app is None
    assert "pywin32" in message


# --------------------------------------------------------------------------
# Чтение коллекций
# --------------------------------------------------------------------------
def test_names_reads_zero_based_collection():
    collection = FakeCollection(["Rough_D16", "Finish_D8"])
    assert pm_com.names(collection) == ["Rough_D16", "Finish_D8"]


def test_names_reads_one_based_collection():
    """Если индексация с единицы — всё равно читаем (фолбэк по Count)."""
    collection = FakeCollection(["Tool_1", "Tool_2"], one_based=True)
    assert pm_com.names(collection) == ["Tool_1", "Tool_2"]


def test_names_reads_enum_only_collection():
    assert pm_com.names(EnumOnlyCollection(["A", "B"])) == ["A", "B"]


def test_names_skips_items_without_name():
    class Empty:
        Count = 2

        def Item(self, index):
            return type("Obj", (), {})()      # объекта без .Name

    assert pm_com.names(Empty()) == []


def test_item_name_prefers_name_attribute():
    class Lower:
        name = "нижний регистр"

    assert pm_com.item_name(Lower()) == "нижний регистр"


# --------------------------------------------------------------------------
# Сессия
# --------------------------------------------------------------------------
def test_session_reads_project_not_active_project():
    """Разведка показала: ActiveProject нет, есть Project."""
    session = pm_com.LiveSession(FakeApp({"tools": ["D16"], "toolpaths": ["Rough"]}))
    assert session.project is not None
    assert session.section_names("tools") == ["D16"]
    assert session.section_names("toolpaths") == ["Rough"]


def test_session_version():
    session = pm_com.LiveSession(FakeApp(version="PowerMill 2026.0.1"))
    assert session.version == "PowerMill 2026.0.1"


def test_session_counts():
    session = pm_com.LiveSession(FakeApp({"models": ["Blok"], "tools": ["D16", "D8"]}))
    counts = session.counts()
    assert counts["models"] == 1
    assert counts["tools"] == 2
    assert counts["levels"] == 0


def test_session_without_project_returns_empty():
    class NoProject:
        Version = "2026"

    session = pm_com.LiveSession(NoProject())
    assert session.project is None
    assert session.section_names("tools") == []
    assert session.read_context()["_total"] == 0


def test_read_context_shape_matches_snapshot_format():
    app = FakeApp({"models": ["Blok_40X"], "tools": ["Rough_D16"],
                   "toolpaths": ["Rough_D16_1"]})
    context = pm_com.LiveSession(app).read_context()

    assert context["models"] == ["Blok_40X"]
    assert context["_total"] == 3
    assert context["_source"].startswith("живой PowerMill")
    assert "_parsed_at" in context


def test_read_context_records_errors_instead_of_crashing():
    class BrokenProject:
        Models = None

    class BrokenApp:
        Project = BrokenProject()
        Version = "2026"

    context = pm_com.LiveSession(BrokenApp()).read_context()
    assert context["_total"] == 0                       # не упали


def test_context_is_usable_by_project_context():
    """Снимок живьём должен пониматься тем же кодом, что и снимок макросом."""
    from src import project_context

    app = FakeApp({"models": ["Blok_40X"], "tools": ["Rough_D16"]})
    context = pm_com.LiveSession(app).read_context()

    text = project_context.summary(context)
    assert "Blok_40X" in text
    block = project_context.to_prompt_block(context)
    assert "Blok_40X" in block


# --------------------------------------------------------------------------
# Выполнение команд
# --------------------------------------------------------------------------
def test_execute_uses_docommand_first():
    app = FakeApp()
    ok, message = pm_com.LiveSession(app).execute('PRINT "тест"')
    assert ok is True
    assert app.commands == ['PRINT "тест"']
    assert "DoCommand" in message


def test_execute_falls_back_to_other_methods():
    class OnlyExecute:
        Project = FakeProject({})

        def __init__(self):
            self.commands: list[str] = []

        def ExecuteEx(self, command):
            self.commands.append(command)

    app = OnlyExecute()
    ok, _message = pm_com.LiveSession(app).execute("MACRO 'x.mac'")
    assert ok is True
    assert app.commands == ["MACRO 'x.mac'"]


def test_execute_explains_when_no_command_method():
    ok, message = pm_com.LiveSession(NoCommandApp()).execute("PRINT 1")
    assert ok is False
    assert "DoCommand" in message


def test_execute_reports_powermill_error():
    class Angry:
        Project = FakeProject({})

        def DoCommand(self, command):
            raise RuntimeError("команда не понравилась")

    ok, message = pm_com.LiveSession(Angry()).execute("БРЕД")
    assert ok is False
    assert "команда не понравилась" in message


def test_save_project_uses_pml_with_windows_slashes():
    app = FakeApp()
    pm_com.LiveSession(app).save_project("E:/powermill-ai/output/blok.pmlprj")
    assert app.commands == ['PROJECT SAVE "E:\\powermill-ai\\output\\blok.pmlprj"']


# --------------------------------------------------------------------------
# Готовые сценарии
# --------------------------------------------------------------------------
def test_refresh_context_without_powermill(monkeypatch):
    monkeypatch.setattr("src.power_mill_link.powermill_running", lambda: False)
    context, message = pm_com.refresh_context()
    assert context is None
    assert "не запущен" in message


def test_refresh_context_saves_snapshot(monkeypatch, tmp_path):
    monkeypatch.setattr(pm_com, "connect",
                        lambda: (pm_com.LiveSession(FakeApp({"models": ["Blok"]})),
                                 "подключено"))
    saved: list = []
    monkeypatch.setattr("src.project_context.save",
                        lambda context: saved.append(context) or tmp_path / "ctx.json")

    context, message = pm_com.refresh_context()
    assert context["_total"] == 1
    assert saved and saved[0]["models"] == ["Blok"]
    assert "ctx.json" in message


def test_refresh_context_marks_empty_project(monkeypatch):
    monkeypatch.setattr(pm_com, "connect",
                        lambda: (pm_com.LiveSession(FakeApp({})), "подключено"))
    context, message = pm_com.refresh_context(save=False)
    assert context is not None
    assert context["_total"] == 0
    assert "не открыт проект" in message


def test_status_lines_show_counts(monkeypatch):
    monkeypatch.setattr(pm_com, "connect",
                        lambda: (pm_com.LiveSession(
                            FakeApp({"tools": ["D16"], "toolpaths": ["Rough"]})),
                            "подключено"))
    text = "\n".join(pm_com.status_lines())
    assert "версия PowerMill" in text
    assert "tools=1" in text and "toolpaths=1" in text


def test_status_lines_explain_when_not_connected(monkeypatch):
    monkeypatch.setattr(pm_com, "connect", lambda: (None, "PowerMill не запущен"))
    text = "\n".join(pm_com.status_lines())
    assert "не запущен" in text


# --------------------------------------------------------------------------
# Отчёт разведки идёт через pm_com (без запуска второй копии)
# --------------------------------------------------------------------------
def test_pm_live_com_strategy_attaches_only(monkeypatch):
    from src import pm_live

    monkeypatch.setattr(pm_com, "attach",
                        lambda progids=None: (None, "PowerMill не запущен"))
    app, message = pm_live.connect_com()
    assert app is None
    assert "не запущен" in message


def test_pm_live_com_strategy_returns_running_app(monkeypatch):
    from src import pm_live

    fake = FakeApp({"tools": ["D16"]})
    monkeypatch.setattr(pm_com, "attach",
                        lambda progids=None: (fake, "подключено через COM"))
    app, message = pm_live.connect_com()
    assert app is fake
    assert "подключено через COM" in message
