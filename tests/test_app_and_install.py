"""
Тесты окна приложения, проверки компьютера и установки (пункты 39–40).

Окно рисуется только при запуске, поэтому здесь проверяется вся «начинка»:
какие кнопки попадают в окно, что и чем запускается, что видно в журнале и как
установщик выбирает папку данных. Экран и Windows для тестов не нужны.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from src import app_window, doctor, pm_buttons, shortcuts


# --------------------------------------------------------------------------
# Окно приложения (пункт 39)
# --------------------------------------------------------------------------
def test_window_uses_the_shared_button_list():
    plans = app_window.plans()
    assert [plan.action.label for plan in plans] == \
        [action.label for action in pm_buttons.pane_actions()]
    groups = app_window.grouped_plans()
    assert [name for name, _items in groups] == \
        [name for name, _items in pm_buttons.pane_groups()]


def test_macro_buttons_run_inside_powermill(tmp_path):
    macro_dir = tmp_path / "output" / "pm_macros"
    macro_dir.mkdir(parents=True)
    (macro_dir / "PM_AI_ASK.mac").write_text("// макрос", encoding="cp1251")
    plan = app_window.plan_for(pm_buttons.by_key("assistant"), tmp_path)
    assert plan.kind == "macro"
    assert plan.command == [str(macro_dir / "PM_AI_ASK.mac")]


def test_missing_macro_is_reported_not_guessed(tmp_path):
    plan = app_window.plan_for(pm_buttons.by_key("snapshot"), tmp_path)
    assert plan.kind == "missing"
    assert "пункт 28" in plan.problem


def test_asking_scenarios_open_a_window():
    """Сценарии с вопросами запускаются отдельным окном — на реальном проекте."""
    project = Path(__file__).resolve().parent.parent
    for key in ("operation", "checks", "nc", "flow", "tool", "cutting"):
        plan = app_window.plan_for(pm_buttons.by_key(key), project)
        assert plan.kind == "window", key
        assert plan.command[0].endswith(".bat"), key
        assert Path(plan.command[0]).exists(), plan.command[0]


def test_quiet_scenario_runs_into_the_log(tmp_path):
    plan = app_window.plan_for(pm_buttons.by_key("chat"), tmp_path)
    assert plan.kind == "inline"
    assert plan.command[1:] == ["-m", "scripts.chat_ui", "--open"]


def test_every_button_has_a_plan(tmp_path):
    for plan in app_window.plans(tmp_path):
        assert plan.kind in ("macro", "window", "inline", "missing")


def test_project_python_prefers_venv(tmp_path):
    scripts = tmp_path / ".venv" / "Scripts"
    scripts.mkdir(parents=True)
    (scripts / "python.exe").write_bytes(b"x")
    assert app_window.project_python(tmp_path) == str(scripts / "python.exe")
    assert app_window.project_python(tmp_path / "нет") == sys.executable


def test_macro_runner_says_when_powermill_is_absent(monkeypatch):
    monkeypatch.setattr(app_window, "header_lines", lambda *a, **k: [])
    from src import pm_com

    monkeypatch.setattr(pm_com, "connect", lambda: (None, "PowerMill не запущен"))
    lines = app_window.run_macro(Path("output/pm_macros/PM_AI_ASK.mac"))
    text = "\n".join(lines)
    assert "не отвечает" in text
    assert "ленте" in text            # подсказка про кнопку на ленте


def test_macro_runner_reports_powermill_answer(monkeypatch):
    from src import pm_com

    class FakeSession:
        version = "2026000"

        def execute(self, command):
            return True, "DoCommand('MACRO ...') -> OK | ответ: выполнено"

    monkeypatch.setattr(pm_com, "connect", lambda: (FakeSession(), "ок"))
    lines = app_window.run_macro(Path("output/pm_macros/PM_AI_ASK.mac"))
    text = "\n".join(lines)
    assert "✔" in text and "DoCommand" in text and "выполнено" in text


# --------------------------------------------------------------------------
# Проверка компьютера (пункт 40)
# --------------------------------------------------------------------------
def test_python_check_accepts_current_interpreter():
    check = doctor.check_python()
    assert check.status in (doctor.STATUS_OK, doctor.STATUS_WARN)


def test_data_root_check_creates_and_writes(tmp_path):
    root = tmp_path / "данные"
    check = doctor.check_data_root(root)
    assert check.status == doctor.STATUS_OK
    assert root.exists()


def test_report_lists_problems_and_advice(tmp_path, monkeypatch):
    report = doctor.DoctorReport()
    report.add("PowerMill установлен", doctor.STATUS_BAD, "не найден",
               "Установи PowerMill")
    report.add("Локальный ИИ", doctor.STATUS_WARN, "ollama не в PATH")
    report.add("Python", doctor.STATUS_OK, "3.12.1")

    text = report.format()
    assert "✘ PowerMill установлен" in text
    assert "Установи PowerMill" in text          # совет виден
    assert "ИТОГ: не готово" in text
    assert "На что посмотреть" in text
    assert report.ready is False
    assert len(report.problems) == 1 and len(report.warnings) == 1


def test_report_ready_when_no_problems():
    report = doctor.DoctorReport()
    report.add("Python", doctor.STATUS_OK, "3.12")
    report.add("PowerMill", doctor.STATUS_WARN, "не запущен")
    assert report.ready is True                  # предупреждение — не ошибка
    assert "компьютер готов" in report.format()
    summary = doctor.quick_summary(report)
    assert "в порядке" in summary or "готов" in summary


def test_collect_without_powermill(tmp_path):
    """Проверки, не связанные с PowerMill, работают и на пустом компьютере."""
    report = doctor.collect(data_root=tmp_path, project_dir=tmp_path,
                            include_powermill=False)
    titles = [check.title for check in report.checks]
    assert "Python" in titles
    assert "Папка данных" in titles
    assert all(check.status in (doctor.STATUS_OK, doctor.STATUS_WARN,
                               doctor.STATUS_BAD, doctor.STATUS_SKIP)
               for check in report.checks)


def test_save_writes_report(tmp_path):
    report = doctor.DoctorReport()
    report.add("Python", doctor.STATUS_OK, "3.12")
    path = doctor.save(report, tmp_path / "doctor_report.txt")
    assert path.exists()
    assert "проверка компьютера" in path.read_text(encoding="utf-8").lower()


def test_ui_check_mentions_tkinter_or_is_ok(tmp_path):
    check = doctor.check_ui(tmp_path)
    assert check.status in (doctor.STATUS_OK, doctor.STATUS_WARN, doctor.STATUS_BAD)
    if check.status != doctor.STATUS_OK:
        assert "tkinter" in check.detail or "иконк" in check.detail


def test_install_settings_check(tmp_path):
    check = doctor.check_install_settings(tmp_path, tmp_path)
    assert check.status == doctor.STATUS_WARN
    (tmp_path / "install.json").write_text("{}", encoding="utf-8")
    assert doctor.check_install_settings(tmp_path, tmp_path).status == doctor.STATUS_OK


def test_module_checks_flag_missing_libraries():
    checks = doctor.check_modules()
    names = [check.title for check in checks]
    assert any(name.startswith("Библиотека requests") for name in names)
    assert any("по желанию" in name for name in names)


# --------------------------------------------------------------------------
# Ярлыки и установка
# --------------------------------------------------------------------------
def test_shortcuts_plan_lists_desktop_and_menu(tmp_path):
    lines = shortcuts.plan_lines(tmp_path, "PowerMill AI")
    text = "\n".join(lines)
    assert "PowerMill AI.lnk" in text
    assert "PowerMill AI — меню пунктов.lnk" in text
    assert "Desktop" in text or "Рабочий стол" in text
    assert "Start Menu" in text or "Пуск" in text


def test_shortcut_command_uses_powershell_com(tmp_path):
    shortcut = shortcuts.Shortcut("PowerMill AI", tmp_path / "start_app.bat",
                                  "desktop", workdir=tmp_path)
    command = shortcuts.powershell_command(shortcut, tmp_path)
    text = " ".join(command)
    assert command[0] == "powershell"
    assert "WScript.Shell" in text
    assert "start_app.bat" in text
    assert "CreateShortcut" in text


def test_shortcut_dry_run_returns_command(tmp_path):
    shortcut = shortcuts.Shortcut("PowerMill AI", tmp_path / "start_app.bat",
                                  "menu", workdir=tmp_path)
    ok, note = shortcuts.create(shortcut, dry_run=True)
    assert ok and "WScript.Shell" in note


def test_app_shortcuts_include_app_menu_and_reports(tmp_path):
    found = shortcuts.app_shortcuts(tmp_path)
    names = [shortcut.name for shortcut in found]
    assert names.count("PowerMill AI") == 2          # рабочий стол + меню «Пуск»
    assert any("меню пунктов" in name for name in names)
    assert any("отчёты" in name for name in names)


# --------------------------------------------------------------------------
# Установщик
# --------------------------------------------------------------------------
def test_installer_module_is_standard_library_only():
    """install.bat запускает его обычным Python — значит, только stdlib."""
    source = (Path(__file__).resolve().parent.parent
              / "scripts" / "install_app.py").read_text(encoding="utf-8")
    for line in source.splitlines():
        if line.startswith("import ") or line.startswith("from "):
            module = line.split()[1].split(".")[0]
            assert module in {"__future__", "argparse", "json", "os", "shutil",
                              "subprocess", "sys", "time", "pathlib", "src"}, module


def test_installer_writes_settings_and_folders(tmp_path, monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "install_app", Path(__file__).resolve().parent.parent
        / "scripts" / "install_app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    monkeypatch.setattr(module, "CODE_DIR", tmp_path)
    printer = module.Printer()
    module.write_settings(tmp_path / "данные")
    settings = (tmp_path / "install.json").read_text(encoding="utf-8")
    assert "data_root" in settings

    made = module.make_folders(tmp_path / "данные", printer)
    assert (tmp_path / "данные" / "output").exists()
    assert (tmp_path / "данные" / "data" / "pdf").exists()
    assert (tmp_path / "данные" / "chroma_db").exists()
    assert len(made) > 5


def test_installer_default_data_root_is_sensible():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "install_app", Path(__file__).resolve().parent.parent
        / "scripts" / "install_app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    root = module.default_data_root()
    assert isinstance(root, Path)
    assert root.name.lower() in ("powermill-ai", "powermillai")


def test_config_reads_install_json(tmp_path):
    """У другого человека настройка берётся из install.json, без переменных.

    Проверяем отдельным процессом: так тест не трогает настройки, уже
    загруженные другими тестами.
    """
    import json
    import os
    import subprocess

    settings = tmp_path / "install.json"
    data_root = tmp_path / "данные"
    settings.write_text(json.dumps({"data_root": str(data_root)}), encoding="utf-8")

    env = dict(os.environ)
    env["POWERMILL_AI_SETTINGS"] = str(settings)
    env.pop("POWERMILL_DATA_ROOT", None)
    project = Path(__file__).resolve().parent.parent

    done = subprocess.run([sys.executable, "-c",
                           "import config; print(config.DATA_ROOT)"],
                          cwd=str(project), env=env, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == str(data_root)
