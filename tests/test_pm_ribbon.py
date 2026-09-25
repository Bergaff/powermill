"""
Тесты пункта 34 — панель «PowerMill AI» на ленте PowerMill.

Настоящего PowerMill и его файла ленты здесь нет, поэтому проверяем главное:

* макросы-запускатели пишутся и вызывают нужные батники;
* вкладка собирается **клонированием** существующей кнопки с макросом, а не по
  выдуманной схеме (схему Autodesk не документирует);
* если кнопки с макросом в файле нет — файл не меняется, а в отчёт попадает
  инструкция для ручного добавления;
* перед изменением делается копия настройки.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from src import pm_macro, pm_ribbon


# Синтетический файл ленты: структура «как бывает у пользователя» — вкладки,
# группы и кнопка, запускающая макрос (её мы и клонируем).
SAMPLE_XML = """<?xml version="1.0" encoding="utf-8"?>
<ribbon_customisation>
  <tabs>
    <tab label="Моя вкладка">
      <group label="Мои кнопки">
        <button label="Мой макрос" tooltip="старый" macro="C:/Temp/Old.mac"/>
        <button label="Ещё один" macro="C:/Temp/Other.mac"/>
      </group>
    </tab>
  </tabs>
</ribbon_customisation>
"""

EMPTY_XML = """<?xml version="1.0" encoding="utf-8"?>
<ribbon_customisation><tabs/></ribbon_customisation>
"""


@pytest.fixture
def ribbon_file(tmp_path, monkeypatch):
    """Файл настройки ленты во временной папке + макросы тоже туда."""
    folder = tmp_path / "Autodesk" / "PowerMill"
    folder.mkdir(parents=True)
    path = folder / "ribbon_customisation.xml"
    path.write_text(SAMPLE_XML, encoding="utf-8")

    monkeypatch.setattr(pm_ribbon, "find_ribbon_file", lambda: path)
    monkeypatch.setattr(pm_ribbon, "REPORT_FILE", tmp_path / "pm_ribbon_report.txt")
    monkeypatch.setattr(pm_macro, "MACRO_DIR", tmp_path / "output" / "pm_macros")
    monkeypatch.setattr(pm_macro, "OUTPUT_DIR", tmp_path / "output")
    return path


# --------------------------------------------------------------------------
# макросы-запускатели
# --------------------------------------------------------------------------
def test_launcher_macro_calls_bat(monkeypatch, tmp_path):
    monkeypatch.setattr(pm_macro, "OUTPUT_DIR", tmp_path / "output")
    text = pm_ribbon.launcher_macro("scripts\\probe_tool.bat")
    assert "OLE FILEACTION 'OPEN'" in text
    assert "RESET LOCALVARS" in text
    # путь в макросе — windows-вид и с одним обратным слэшем
    assert "probe_tool.bat" in text
    assert chr(92) * 2 not in text


def test_write_launcher_macros_skips_existing_ones(ribbon_file):
    written = pm_ribbon.write_launcher_macros()
    names = {path.name for path in written}
    assert "PM_AI_CHAT.mac" in names
    assert "PM_AI_TOOL.mac" in names
    assert "PM_AI_OPERATION.mac" in names
    # ассистент и снимок — это наши обычные макросы, их не перезаписываем
    assert "PM_AI_ASK.mac" not in names
    assert "PM_AI_SNAPSHOT.mac" not in names
    for path in written:
        raw = path.read_bytes()
        assert b"\r\n" in raw                     # CRLF, как у макросов PowerMill
        raw.decode("cp1251")                      # CP1251, а не UTF-8


def test_launcher_macros_pass_own_validator(ribbon_file):
    from src import pml_vocab

    vocab = pml_vocab.load_vocabulary()
    for path in pm_ribbon.write_launcher_macros():
        report = pml_vocab.validate(path.read_bytes().decode("cp1251"), vocab)
        assert report["ok"], path.name


# --------------------------------------------------------------------------
# сборка вкладки
# --------------------------------------------------------------------------
def test_build_tab_clones_existing_button():
    root = ET.fromstring(SAMPLE_XML)
    ok, note = pm_ribbon.build_tab(root)
    assert ok, note

    text = ET.tostring(root, encoding="unicode")
    assert "PowerMill AI" in text
    for label, macro_name, _target, _hint in pm_ribbon.RIBBON_BUTTONS:
        assert label in text
        assert macro_name in text              # кнопки ссылаются на наши макросы
    # чужие настройки не тронуты
    assert "Моя вкладка" in text and "C:/Temp/Old.mac" in text


def test_build_tab_keeps_attribute_names_from_sample():
    """Имена атрибутов берём из файла пользователя, а не выдумываем."""
    xml = SAMPLE_XML.replace("macro=", "commandFile=")
    root = ET.fromstring(xml)
    ok, _note = pm_ribbon.build_tab(root)
    assert ok
    text = ET.tostring(root, encoding="unicode")
    assert "commandFile=" in text
    assert "macro=" not in text


def test_build_tab_without_macro_button_does_nothing():
    root = ET.fromstring(EMPTY_XML)
    before = ET.tostring(root, encoding="unicode")
    ok, note = pm_ribbon.build_tab(root)
    assert ok is False
    assert "нет кнопки" in note
    assert ET.tostring(root, encoding="unicode") == before   # файл не тронут


def test_structure_lines_describe_file():
    root = ET.fromstring(SAMPLE_XML)
    lines = pm_ribbon.structure_lines(root)
    text = "\n".join(lines)
    assert "<tab" in text and "<group" in text and "<button" in text
    assert "Моя вкладка" in text


# --------------------------------------------------------------------------
# установка
# --------------------------------------------------------------------------
def test_install_adds_tab_and_makes_backup(ribbon_file):
    result = pm_ribbon.install(apply_in_powermill=False)

    assert result.tab_added is True
    assert result.backup is not None and result.backup.exists()
    assert SAMPLE_XML in result.backup.read_text(encoding="utf-8")   # копия прежней настройки

    fresh = ribbon_file.read_text(encoding="utf-8")
    assert "PowerMill AI" in fresh and "PM_AI_CHAT.mac" in fresh
    assert "<?xml" in fresh                       # объявление версии сохранили
    ET.fromstring(fresh)                          # и файл остался валидным XML


def test_install_skips_when_tab_already_there(ribbon_file):
    first = pm_ribbon.install(apply_in_powermill=False)
    assert first.tab_added

    second = pm_ribbon.install(apply_in_powermill=False)
    assert second.tab_added is False
    assert any("уже есть" in note for note in second.notes)


def test_install_without_ribbon_file_gives_instructions(monkeypatch, tmp_path):
    monkeypatch.setattr(pm_ribbon, "find_ribbon_file", lambda: None)
    monkeypatch.setattr(pm_macro, "MACRO_DIR", tmp_path / "pm_macros")
    result = pm_ribbon.install(apply_in_powermill=False)

    assert result.tab_added is False
    joined = "\n".join(result.notes)
    assert "Customise the Ribbon" in joined          # инструкция для ручного пути
    assert result.launchers                            # макросы всё равно выложены


def test_install_applies_commands_in_live_powermill(ribbon_file):
    class FakeSession:
        def __init__(self):
            self.commands: list[str] = []

        def execute(self, command: str):
            self.commands.append(command)
            return True, "OK"

    session = FakeSession()
    result = pm_ribbon.install(apply_in_powermill=True, session=session)

    assert result.applied is True
    assert any("EDIT CUSTOMRIBBON IMPORT FILEOPEN" in c for c in session.commands)
    assert "EDIT CUSTOMRIBBON APPLY" in session.commands
    assert "FORM RIBBON TAB UICATEGORY" in session.commands


def test_install_reports_failed_apply(ribbon_file):
    class BadSession:
        def execute(self, command: str):
            return False, "недопустимый элемент или команда"

    result = pm_ribbon.install(apply_in_powermill=True, session=BadSession())
    assert result.tab_added is True          # файл изменён
    assert result.applied is False           # но применить не удалось
    assert any("перезапусти PowerMill" in note for note in result.notes)


def test_report_is_written(ribbon_file, tmp_path):
    result = pm_ribbon.install(apply_in_powermill=False)
    path = pm_ribbon.save_report(result)
    text = path.read_text(encoding="utf-8")
    assert "PowerMill AI" in text
    assert "Файл настройки ленты" in text
    assert "Структура файла ленты" in text


def test_utf16_ribbon_file_is_read_and_written_back(ribbon_file):
    """Autodesk пишет настройку и в UTF-16 — читаем и сохраняем в той же кодировке."""
    ribbon_file.write_bytes(SAMPLE_XML.encode("utf-16"))
    result = pm_ribbon.install(apply_in_powermill=False)
    assert result.tab_added is True
    raw = ribbon_file.read_bytes()
    assert raw[:2] in (b"\xff\xfe", b"\xfe\xff")          # остался UTF-16
    assert "PowerMill AI" in raw.decode("utf-16")


def test_find_ribbon_file_in_localappdata(tmp_path, monkeypatch):
    folder = tmp_path / "Autodesk" / "PowerMill 2026"
    folder.mkdir(parents=True)
    target = folder / "ribbon_customisation.xml"
    target.write_text("<x/>", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("APPDATA", raising=False)
    assert pm_ribbon.find_ribbon_file() == target


def test_find_ribbon_file_returns_none_when_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("APPDATA", raising=False)
    assert pm_ribbon.find_ribbon_file() is None
