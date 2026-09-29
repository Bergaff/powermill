"""Проверки «связки с PowerMill» одним запуском (пункт 47).

PowerMill в песочнице нет, поэтому мост и запуск макроса подменяются: тесты
проверяют то, что от них не зависит, — порядок шагов, вопросы человеку,
текст отчёта, код возврата для батника и что без согласия ничего не ставится.
"""
from __future__ import annotations

import json
from pathlib import Path

import config
from src import link_check, pm_macro

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _report(roundtrip=True, advice=None) -> link_check.LinkReport:
    report = link_check.LinkReport()
    report.add("pywin32", "ok", "модуль на месте")
    report.add("com", "ok", "подключён, версия 26.0.0")
    report.add("project", "ok", "models: 1, tools: 2")
    report.add("roundtrip", "ok" if roundtrip else "fail",
               "PowerMill выполнил наш макрос" if roundtrip else "файлы-отметки не обновились")
    report.roundtrip = roundtrip
    report.advice.extend(advice or [])
    return report


def _quiet(monkeypatch, link_setup, report, bridges_ok=True, answers=(True,)):
    """Общая обвязка: тихий вывод, подменённые мост/макросы/проверка связи."""
    from src import pm_com

    monkeypatch.setattr(pm_com, "bridges", lambda: {"pywin32": bridges_ok})
    monkeypatch.setattr(pm_macro, "write_all", lambda folder=None: [Path("PM_AI_TEST.mac")])
    monkeypatch.setattr(pm_macro, "copy_into_power_mill", lambda names=None: ([], []))
    monkeypatch.setattr(link_setup.link_check, "run", lambda with_roundtrip=True: report)
    monkeypatch.setattr(link_setup, "start_log", lambda name: Path("лог.txt"))
    queue = iter(answers)
    monkeypatch.setattr(link_setup, "_ask_yes",
                        lambda question, default_yes=True: next(queue, default_yes))
    return []


def test_run_goes_in_order_and_returns_success(monkeypatch, tmp_path, capfd):
    from scripts import link_setup

    lines = _quiet(monkeypatch, link_setup, _report(roundtrip=True))
    ok, notes, report = link_setup.run(print_=lines.append)
    assert ok is True
    text = "\n".join(lines)
    # порядок шагов: мост → макросы → проверка делом
    assert text.index("[1/3] Мост") < text.index("[2/3] Макросы")
    assert text.index("[2/3] Макросы") < text.index("[3/3] Проверка связи делом")
    assert "powermill выполнил нашу команду" in text.lower()


def test_report_file_is_ready_to_send(monkeypatch, tmp_path):
    from scripts import link_setup

    _quiet(monkeypatch, link_setup, _report(roundtrip=False))
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    assert link_setup.main() == 1                 # не получилось — честный код 1
    path = tmp_path / "pm_link_setup_report.txt"
    text = path.read_text(encoding="utf-8")
    assert "пункт 47" in text
    assert "мост (27) → макросы (28) → проверка делом (41)" in text
    assert "прислать в чат" in text
    assert "ИТОГ:" in text


def test_main_returns_zero_when_roundtrip_worked(monkeypatch, tmp_path):
    from scripts import link_setup

    _quiet(monkeypatch, link_setup, _report(roundtrip=True))
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    assert link_setup.main() == 0


def test_without_consent_nothing_is_installed(monkeypatch, capfd):
    """Ответ «н» на предложение поставить мост — ставить не имеем права."""
    from scripts import link_setup
    import scripts.install_bridge as install_bridge

    def forbidden(*args, **kwargs):
        raise AssertionError("без согласия человека ставить нельзя")

    monkeypatch.setattr(install_bridge, "pip_install", forbidden)
    _quiet(monkeypatch, link_setup, _report(roundtrip=False), bridges_ok=False,
           answers=(False,))
    ok, notes, _report_obj = link_setup.run(print_=print)
    assert ok is False
    assert any("27" in note for note in notes)


def test_with_consent_installs_the_bridge(monkeypatch, capfd):
    from scripts import link_setup
    import scripts.install_bridge as install_bridge

    asked: list[str] = []
    monkeypatch.setattr(install_bridge, "pip_install",
                        lambda package: asked.append(package) or (True, "установлено"))
    monkeypatch.setattr(install_bridge, "check_package",
                        lambda modules: (True, "import ok (win32com.client)"))
    _quiet(monkeypatch, link_setup, _report(roundtrip=True), bridges_ok=False,
           answers=(True,))
    ok, notes, _report_obj = link_setup.run(print_=print)
    assert ok is True
    assert asked == ["pywin32"]
    assert any("поставлен" in note for note in notes)


def test_failed_install_explains_itself(monkeypatch, capfd):
    from scripts import link_setup
    import scripts.install_bridge as install_bridge

    monkeypatch.setattr(install_bridge, "pip_install",
                        lambda package: (False, "таймаут установки"))
    _quiet(monkeypatch, link_setup, _report(roundtrip=False), bridges_ok=False)
    ok, notes, _report_obj = link_setup.run(print_=print)
    assert ok is False
    assert any("таймаут" in note for note in notes)


def test_prepare_macros_says_where_they_are_when_no_folders(monkeypatch, tmp_path):
    from scripts import link_setup

    monkeypatch.setattr(pm_macro, "write_all", lambda folder=None: [tmp_path / "PM_AI_TEST.mac"])
    monkeypatch.setattr(pm_macro, "copy_into_power_mill", lambda names=None: ([], []))
    monkeypatch.setattr(pm_macro, "power_mill_macro_folders", lambda: [])
    lines: list[str] = []
    copied, notes = link_setup.prepare_macros(lines.append)
    text = "\n".join(lines)
    assert copied == 0
    assert "Macro Paths" in text or "Пути макросов" in text
    assert notes                                     # подсказку не потеряли


def test_copy_helper_copies_and_survives_readonly_folder(monkeypatch, tmp_path):
    """Копирование в PowerMill: одна папка пишется, вторая — только для чтения."""
    macro_dir = tmp_path / "macros"
    macro_dir.mkdir()
    (macro_dir / "PM_AI_TEST.mac").write_text("PRINT 1\n", encoding="cp1251")
    good = tmp_path / "pm" / "lib" / "macro"
    good.mkdir(parents=True)
    readonly = tmp_path / "program files" / "macro"
    readonly.mkdir(parents=True)

    monkeypatch.setattr(pm_macro, "MACRO_DIR", macro_dir)
    monkeypatch.setattr(pm_macro, "power_mill_macro_folders", lambda: [good, readonly])

    import shutil

    original_copy2 = shutil.copy2          # берём ДО подмены, иначе рекурсия

    def fake_copy2(source, target):
        if str(target).startswith(str(readonly)):
            raise PermissionError(13, "Access is denied")
        original_copy2(source, target)

    monkeypatch.setattr(shutil, "copy2", fake_copy2)
    copied, failed = pm_macro.copy_into_power_mill(["PM_AI_TEST.mac"])
    assert [path.parent for path in copied] == [good]
    assert failed and failed[0][0] == readonly
    assert "Access is denied" in failed[0][1]


def test_bat_is_double_clickable_and_mentions_the_chain():
    text = (PROJECT_ROOT / "scripts" / "link_setup.bat").read_text(
        encoding="utf-8", errors="replace")
    assert "chcp 65001" in text
    assert ".venv\\Scripts\\python.exe" in text and "venv\\Scripts\\python.exe" in text
    assert "scripts.link_setup" in text
    for point in ("пункт 27", "пункт 28", "пункт 41"):
        assert point in text
    assert "pm_link_setup_report.txt" in text
    assert "pause" in text                     # окно не закрывается молча


def test_menu_has_point_47():
    text = (PROJECT_ROOT / "start_menu.bat").read_text(encoding="utf-8", errors="replace")
    assert "Выбор (0-47)" in text
    assert '"%choice%"=="47" goto linksetup' in text
    assert "scripts\\link_setup.bat" in text
    assert "47  -  Связка с PowerMill" in text


def test_report_is_visible_where_reports_live():
    """Отчёт связки должен быть виден там же, где остальные (пункт 29, окно)."""
    from scripts import show_reports

    text = (PROJECT_ROOT / "scripts" / "show_reports.py").read_text(encoding="utf-8")
    assert "pm_link_setup_report.txt" in text
    webui = (PROJECT_ROOT / "src" / "webui.py").read_text(encoding="utf-8")
    assert "pm_link_setup_report.txt" in webui
    mcp = (PROJECT_ROOT / "src" / "mcp_server.py").read_text(encoding="utf-8")
    assert "pm_link_setup_report.txt" in mcp
    assert callable(show_reports.main)
