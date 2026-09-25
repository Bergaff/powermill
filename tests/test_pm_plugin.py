"""
Тесты плагина-панели (шаг 2.3б, пункт 38).

Компилятора C# в песочнице нет, поэтому проверяем то, что можно проверить
честно: исходник собирается по фактам каркаса Autodesk, пути в нём не
задваиваются, все кнопки ссылаются на существующие сценарии, команды сборки и
регистрации — правильные, а отчёт всегда говорит, что НЕ проверено.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src import pm_plugin

PROJECT = Path(__file__).resolve().parent.parent


def spec(**kwargs) -> pm_plugin.PluginSpec:
    data = {"python_exe": Path(r"E:\powermill-ai\.venv\Scripts\python.exe")}
    data.update(kwargs)
    return pm_plugin.PluginSpec(**data)


def unescape(literal: str) -> str:
    """Возвращает строку, которую увидит C# (проверяем, что путь не задвоён)."""
    return literal.replace("\\\\", "\\").replace('\\"', '"')


# --------------------------------------------------------------------------
# исходник
# --------------------------------------------------------------------------
def test_source_is_built_from_autodesk_facts():
    code = pm_plugin.build_source(spec())
    assert "using Delcam.Plugins.Framework;" in code
    assert "class PowerMillAI : PluginFrameworkWithPanes" in code
    assert '[Guid("' + pm_plugin.PLUGIN_GUID + '")]' in code
    assert "[ClassInterface(ClassInterfaceType.None)]" in code
    assert "[ComVisible(true)]" in code
    assert "register_pane(new PaneDefinition(m_pane, 900, 375, \"PowerMill AI\", null));" in code
    assert "override Guid PluginGuid" in code


def test_source_has_no_unfilled_placeholders():
    for ui in ("wpf", "winforms"):
        code = pm_plugin.build_source(spec(ui=ui))
        assert re.findall(r"@@[A-Z_]+@@", code) == []


def test_source_runs_macros_inside_powermill():
    """Кнопки-макросы панель выполняет в самом PowerMill, а не через батник."""
    code = pm_plugin.build_source(spec())
    # команда PowerMill собирается в C#-строке: "MACRO "<путь>""
    assert 'string command = "MACRO' in code
    assert 'path.Replace' in code
    assert "setup_framework(string token, PluginServices services" in code
    assert "Marshal.GetActiveObject(\"PowerMill.Application\")" in code
    for method in ("DoCommand", "ExecuteEx", "Execute"):
        assert method in code, method        # способы перебираются, а не выдуманы
    assert "services." in code              # сначала пробуем службы плагина


def test_source_marks_window_buttons_and_macro_buttons():
    code = pm_plugin.build_source(spec())
    assert "— окно" in code                 # батники со вопросами
    assert "▶ " in code                     # макросы внутри PowerMill
    for folder in pm_plugin.MACRO_FOLDERS:
        assert folder in code


def test_source_paths_are_escaped_exactly_once():
    """Путь в C#-литерале должен совпадать с настоящим (а не задваиваться)."""
    python = Path(r"E:\powermill-ai\.venv\Scripts\python.exe")
    code = pm_plugin.build_source(spec(python_exe=python, project_dir=Path(r"E:\powermill-ai")))
    python_line = next(l for l in code.splitlines() if "PYTHON =" in l)
    project_line = next(l for l in code.splitlines() if "PROJECT =" in l)
    literal = python_line.split('"', 1)[1].rsplit('"', 1)[0]
    project_literal = project_line.split('"', 1)[1].rsplit('"', 1)[0]
    assert unescape(literal) == str(python)
    assert unescape(project_literal) == r"E:\powermill-ai"


def test_source_has_balanced_braces_and_the_ui_variants():
    for ui in ("wpf", "winforms"):
        code = pm_plugin.build_source(spec(ui=ui))
        assert code.count("{") == code.count("}")
        assert code.count("(") == code.count(")")
    wpf = pm_plugin.build_source(spec(ui="wpf"))
    assert "using System.Windows;" in wpf and "UserControl" in wpf
    winforms = pm_plugin.build_source(spec(ui="winforms"))
    assert "System.Windows.Forms.UserControl" in winforms
    assert "System.Windows.Controls" not in winforms


def test_every_button_points_to_a_real_scenario():
    """Кнопка запускает наш макрос, существующий батник или реальный модуль."""
    kinds = set()
    for button in pm_plugin.PANE_BUTTONS:
        kinds.add(button.kind)
        if button.kind == "macro":
            assert button.target.endswith(".mac"), button.target
        elif button.kind == "bat":
            # в исходнике путь записан по-виндовому — проверяем и его, и файл
            assert (PROJECT / button.target.replace("\\", "/")).exists(), button.target
        else:
            module = PROJECT / (button.target.replace(".", "/") + ".py")
            package = PROJECT / button.target.replace(".", "/") / "__init__.py"
            assert module.exists() or package.exists(), button.target
    assert kinds == {"macro", "bat", "inline"}   # все три вида кнопок есть


def test_pane_buttons_come_from_the_shared_list():
    """Панель и лента — из одного списка (src\\pm_buttons.py)."""
    from src import pm_buttons

    assert len(pm_plugin.PANE_BUTTONS) == len(pm_buttons.pane_actions())
    assert [b.label for b in pm_plugin.PANE_BUTTONS] == \
        [a.label for a in pm_buttons.pane_actions()]
    assert [name for name, _items in pm_plugin.pane_groups()] == \
        [name for name, _items in pm_buttons.pane_groups()]


def test_pane_has_macro_buttons_that_run_inside_powermill():
    macros = [b for b in pm_plugin.PANE_BUTTONS if b.kind == "macro"]
    assert {b.target for b in macros} >= {"PM_AI_ASK.mac", "PM_AI_SNAPSHOT.mac"}


def test_buttons_that_ask_questions_open_a_window():
    """Сценарий, который спрашивает технолога, нельзя запускать «в панель»."""
    code = pm_plugin.build_source(spec())
    assert code.count("AddButton(panel,") == len(pm_plugin.PANE_BUTTONS)
    assert "— окно" in code
    for button in pm_plugin.PANE_BUTTONS:
        if button.bat:
            assert f'"{pm_plugin.cs_str(button.bat)}"' in code, button.label


def test_version_literal_from_user_text():
    code = pm_plugin.build_source(spec(pm_version="2026.0"))
    assert "new Version(2026, 0)" in code
    # одна цифра тоже годится: Version(major, minor) — дописываем ноль
    assert "new Version(2026, 0)" in pm_plugin.build_source(spec(pm_version="2026"))


def test_source_written_with_bom_and_crlf(tmp_path):
    path = pm_plugin.write_source(spec(output_dir=tmp_path))
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "без BOM csc может не понять русский текст"
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")


# --------------------------------------------------------------------------
# окружение, команды сборки и регистрации
# --------------------------------------------------------------------------
def test_find_references_scans_given_folders(tmp_path):
    (tmp_path / "Delcam.Plugins.Framework.dll").write_bytes(b"x")
    (tmp_path / "PowerMILL.dll").write_bytes(b"x")
    (tmp_path / "не_нужное.dll").write_bytes(b"x")
    found = pm_plugin.find_references(extra_dirs=[tmp_path])
    assert [Path(p).name for p in found["framework"]] == ["Delcam.Plugins.Framework.dll"]
    assert [Path(p).name for p in found["extra"]] == ["PowerMILL.dll"]


def test_check_environment_reports_what_is_missing():
    problems = "\n".join(pm_plugin.check_environment({"csc.exe": None, "regasm.exe": None},
                                                     {"framework": [], "extra": []},
                                                     spec(python_exe=None)))
    assert "csc.exe" in problems and "regasm.exe" in problems
    assert "Delcam.Plugins.Framework.dll" in problems
    assert "Python проекта" in problems


def test_check_environment_is_clean_when_ready(tmp_path):
    tools = {"csc.exe": r"C:\csc.exe", "regasm.exe": r"C:\regasm.exe"}
    references = {"framework": [str(tmp_path / "Delcam.Plugins.Framework.dll")], "extra": []}
    assert pm_plugin.check_environment(tools, references, spec()) == []


def test_compile_command_uses_csc_and_references(tmp_path):
    references = {"framework": [r"C:\pm\Delcam.Plugins.Framework.dll"], "extra": []}
    command = pm_plugin.compile_command(spec(output_dir=tmp_path), r"C:\csc.exe", references)
    assert command[0] == r"C:\csc.exe"
    assert "/target:library" in command
    assert f"/out:{tmp_path / 'PowerMillAI.dll'}" in command
    assert "/reference:C:\\pm\\Delcam.Plugins.Framework.dll" in command
    assert command[-1].endswith("PowerMillAI.cs")


def test_register_commands_include_powermill_category():
    """Без компонентной категории PowerMill плагин не подхватывает."""
    commands = pm_plugin.register_commands(spec(), r"C:\regasm.exe")
    flat = [" ".join(item) for item in commands]
    assert any("regasm.exe" in item and "/register /codebase" in item for item in flat)
    for category in pm_plugin.PLUGIN_CATEGORY_GUIDS:
        key = f"Implemented Categories\\{category}"
        views = [item for item in flat if key in item]
        assert len(views) == 2, f"нужны оба разряда реестра для {category}"
        assert any("/reg:32" in item for item in views)
        assert any("/reg:64" in item for item in views)


def test_unregister_commands_remove_registration():
    commands = pm_plugin.unregister_commands(spec(), r"C:\regasm.exe")
    flat = [" ".join(item) for item in commands]
    assert any("/unregister" in item for item in flat)
    assert sum(1 for item in flat if "reg delete" in item) == 2 * len(
        pm_plugin.PLUGIN_CATEGORY_GUIDS)


def test_plan_lines_show_buttons_and_missing_pieces(tmp_path):
    text = "\n".join(pm_plugin.plan_lines(spec(output_dir=tmp_path),
                                          {"csc.exe": None, "regasm.exe": None},
                                          {"framework": [], "extra": []}))
    assert f"кнопок на панели: {len(pm_plugin.PANE_BUTTONS)}" in text
    assert "из того же списка, что лента" in text
    assert "выполнить макрос PM_AI_ASK.mac внутри PowerMill" in text
    assert "НЕ НАЙДЕН" in text
    assert "— не найден" in text


# --------------------------------------------------------------------------
# разбор вывода компилятора и отчёт
# --------------------------------------------------------------------------
def test_parse_build_output_separates_errors_and_warnings():
    text = ("PowerMillAI.cs(12,5): error CS0246: не найден тип «Нечто»\n"
            "PowerMillAI.cs(40,9): warning CS0168: переменная объявлена, но не используется\n"
            "Microsoft (R) Visual C# Compiler\n")
    errors, warnings = pm_plugin.parse_build_output(text)
    assert len(errors) == 1 and "CS0246" in errors[0]
    assert len(warnings) == 1 and "CS0168" in warnings[0]


def test_format_result_always_lists_what_is_not_checked(tmp_path):
    dll = tmp_path / "PowerMillAI.dll"
    dll.write_bytes(b"x" * 10)
    text = pm_plugin.format_result([], [], [], dll)
    assert str(dll) in text
    assert "не проверялся компилятором" in text
    assert "появится в PowerMill" in text


def test_format_result_shows_problems_and_errors():
    text = pm_plugin.format_result(["нет csc.exe"], ["error CS1002: ;"], [], None)
    assert "Сборка сейчас невозможна" in text
    assert "нет csc.exe" in text
    assert "error CS1002" in text


def test_report_file_written(tmp_path, monkeypatch):
    monkeypatch.setattr(pm_plugin, "REPORT_FILE", tmp_path / "pm_plugin_build_report.txt")
    path = pm_plugin.report([], ["  1. исходник"], "Замечаний нет.", None)
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "шаг 2.3б" in text
    assert "Проверка окружения:" in text


def test_report_says_environment_is_ok_when_no_problems(tmp_path, monkeypatch):
    monkeypatch.setattr(pm_plugin, "REPORT_FILE", tmp_path / "pm_plugin_build_report.txt")
    text = pm_plugin.report([], [], "Замечаний нет.", None).read_text(encoding="utf-8")
    assert "✔ всё на месте" in text


def test_python_exe_finds_venv(tmp_path):
    scripts = tmp_path / ".venv" / "Scripts"
    scripts.mkdir(parents=True)
    (scripts / "python.exe").write_bytes(b"x")
    assert pm_plugin.python_exe(tmp_path) == scripts / "python.exe"
    assert pm_plugin.python_exe(tmp_path / "нет") is None
