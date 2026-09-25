"""Тесты подготовки плагина PowerMill (шаг 2.2).

Стенд повторяет структуру установки PowerMill: папка file\\plugins с
Documentation, Framework, Installers, Solutions, как описано в официальном
руководстве Autodesk.
"""
from __future__ import annotations

import pytest

from src import plugin_scaffold as ps

EXAMPLE_CS = """using System;
using System.Windows.Forms;
using Delcam.PowerMILL;

namespace MyPlugin
{
    [Guid("C4227733-9F28-4193-B20E-48D8D9CA049F")]
    public class MyPlugin : PluginBase
    {
    }

    public interface IMyPlugin
    {
    }
}
"""


@pytest.fixture
def install(tmp_path):
    """Установка PowerMill с папкой плагинов."""
    root = tmp_path / "PowerMill 2026"
    plugins = root / "file" / "plugins"
    for sub in ("Documentation", "Framework", "Installers", "Solutions"):
        (plugins / sub).mkdir(parents=True)
    (plugins / "Documentation" / "как_писать_плагин.pdf").write_text("x", encoding="utf-8")
    (plugins / "Framework" / "PluginFramework.csproj").write_text("<Project/>", encoding="utf-8")
    (plugins / "Framework" / "PluginFramework.dll").write_text("dll", encoding="utf-8")
    (plugins / "Solutions" / "Example").mkdir()
    (plugins / "Solutions" / "Example" / "MyPlugin.cs").write_text(EXAMPLE_CS, encoding="utf-8")
    return root


# --------------------------------------------------------------------------
# Поиск
# --------------------------------------------------------------------------
def test_plugin_folder_found(install):
    folder = ps.plugin_folder(install)
    assert folder is not None
    assert folder.name == "plugins"


def test_plugin_folder_absent(tmp_path):
    (tmp_path / "PowerMill 2026").mkdir()
    assert ps.plugin_folder(tmp_path / "PowerMill 2026") is None


def test_find_plugin_dirs_from_explicit_path(install):
    found = ps.find_plugin_dirs([str(install / "file" / "plugins")])
    assert found and found[0].name == "plugins"


def test_read_sources_finds_example(install):
    files = ps.read_sources(ps.plugin_folder(install))
    names = {p.name for p in files}
    assert "MyPlugin.cs" in names
    assert "PluginFramework.csproj" in names


def test_facts_from_sources(install):
    files = ps.read_sources(ps.plugin_folder(install))
    facts = ps.facts_from_sources(files)
    assert any("MyPlugin" in c for c in facts["classes"])
    assert "IMyPlugin" in facts["interfaces"]
    assert facts["guids"] == ["C4227733-9F28-4193-B20E-48D8D9CA049F"]
    assert "System.Windows.Forms" in facts["usings"]


# --------------------------------------------------------------------------
# Копирование и скрипты сборки
# --------------------------------------------------------------------------
def test_copy_install_files(install, tmp_path):
    target = tmp_path / "копия"
    stats = ps.copy_install_files(ps.plugin_folder(install), target)
    assert stats["Solutions"] >= 1
    assert (target / "Solutions" / "Example" / "MyPlugin.cs").exists()


def test_write_build_scripts_uses_found_tools(tmp_path):
    written = ps.write_build_scripts(tmp_path, {"csc.exe": r"C:\csc.exe",
                                                "regasm.exe": r"C:\regasm.exe"},
                                     r"C:\pm\Framework.dll")
    names = {p.name for p in written}
    assert names == {"build.bat", "register.bat"}
    build = (tmp_path / "build.bat").read_text(encoding="utf-8")
    assert r"C:\csc.exe" in build
    assert r"C:\pm\Framework.dll" in build
    register = (tmp_path / "register.bat").read_text(encoding="utf-8")
    assert "/register /codebase" in register


def test_build_script_explains_missing_files(tmp_path):
    ps.write_build_scripts(tmp_path, {}, "")
    build = (tmp_path / "build.bat").read_text(encoding="utf-8")
    assert "no_framework" in build          # есть понятная ветка ошибки
    assert "cmd" not in build.lower().replace("command", "")  # без CLI-инструкций


# --------------------------------------------------------------------------
# Отчёт
# --------------------------------------------------------------------------
def test_report_without_plugin_folder(monkeypatch):
    monkeypatch.setattr(ps, "find_plugin_dirs", lambda extra=None: [])
    text, found = ps.report()
    assert found is False
    assert "не найдена" in text


def test_report_with_plugin_folder(monkeypatch, install, tmp_path):
    monkeypatch.setattr(ps, "find_plugin_dirs",
                        lambda extra=None: [ps.plugin_folder(install)])
    monkeypatch.setattr(ps, "COPY_DIR", tmp_path / "копия")
    monkeypatch.setattr(ps, "PLUGIN_ROOT", tmp_path / "plugin")
    text, found = ps.report()
    assert found is True
    assert "Framework" in text
    assert "классы" in text
    assert "csc.exe" in text
