"""Тесты шага 3.1 — запись режимов резания в проект PowerMill (пункт 30).

Проверяем главное обещание: команды берутся из реальных макросов Autodesk,
макрос показывает, что сделает, читает значения обратно и не трогает то,
о чём его не просили.
"""
from __future__ import annotations

from pathlib import Path

from src import pml_files, pm_edit, pml_vocab

VOCAB = {"entities": ["model", "boundary", "tool", "toolpath", "workplane",
                      "ncprogram", "stockmodel", "pattern"], "parameters": []}


# --------------------------------------------------------------------------
# Макрос правки
# --------------------------------------------------------------------------
def test_macro_passes_own_validator():
    edits = [pm_edit.SpeedFeed("Rough_D16", 4500, 1200, 400)]
    report = pml_vocab.validate(pm_edit.edit_macro(edits), VOCAB)
    assert report["ok"], pml_vocab.format_check(report)


def test_macro_resets_vars_and_writes_result_file():
    text = pm_edit.edit_macro([pm_edit.SpeedFeed("TP1", 4500)])
    assert "RESET LOCALVARS" in text.splitlines()[:15]
    assert "FILE OPEN $pm_result_file FOR WRITE AS out" in text
    assert "FILE CLOSE out" in text
    assert "MESSAGE INFO" in text and "MESSAGE WARN" in text


def test_macro_writes_only_named_params():
    """Не просили менять подачу — макрос её не трогает."""
    text = pm_edit.edit_macro([pm_edit.SpeedFeed("TP1", spindle=4500)])
    assert "$e1_tp.SpindleSpeed.Value = 4500" in text
    assert "Feedrate.Cutting.Value =" not in text
    assert "Feedrate.Plunging.Value =" not in text


def test_macro_reads_values_before_and_after():
    """«Было → стало» читает сам PowerMill — иначе отчёту нельзя верить."""
    text = pm_edit.edit_macro([pm_edit.SpeedFeed("TP1", 4500, 1200)])
    assert "REAL $e1_s0 = $e1_tp.SpindleSpeed.Value" in text
    assert "REAL $e1_s1 = $e1_tp.SpindleSpeed.Value" in text
    assert "REAL $e1_f0 = $e1_tp.Feedrate.Cutting.Value" in text
    assert "REAL $e1_f1 = $e1_tp.Feedrate.Cutting.Value" in text


def test_fallback_uses_real_powermill_commands():
    """Резервный способ — команды из рабочего макроса Autodesk, не догадки."""
    text = pm_edit.edit_macro([pm_edit.SpeedFeed("TP1", 4500, 1200, 400)])
    assert "ACTIVATE TOOLPATH $e1_tp" in text
    assert "EDIT TPPAGE SWFeedSpeed" in text
    assert 'EDIT RPM "4500"' in text
    assert 'EDIT FRATE "1200"' in text
    assert 'EDIT PRATE "400"' in text
    # резерв идёт только если параметр не изменился
    assert "IF $e1_s1 != 4500 {" in text


def test_macro_uses_entity_function_with_real_name():
    text = pm_edit.edit_macro([pm_edit.SpeedFeed("Rough D16", 4500)])
    assert "entity('toolpath','Rough D16')" in text


def test_write_macro_uses_windows_line_endings(tmp_path):
    path = pm_edit.write_macro([pm_edit.SpeedFeed("TP1", 4500)],
                               path=tmp_path / "pm_edit.mac",
                               result_file=tmp_path / "pm_edit_result.txt")
    data = path.read_bytes()
    assert b"\r\n" in data
    assert b"\n" not in data.replace(b"\r\n", b"")
    assert str(tmp_path / "pm_edit_result.txt").replace("\\", "/") in \
        pml_files.decode(data)


def test_preview_shows_assignments():
    lines = pm_edit.preview([pm_edit.SpeedFeed("TP1", 4500, 1200)])
    text = "\n".join(lines)
    assert "TP1" in text
    assert "$tp.SpindleSpeed.Value = 4500" in text
    assert "$tp.Feedrate.Cutting.Value = 1200" in text
    assert "нечего менять" not in text


def test_preview_of_empty_edit():
    assert "нечего менять" in "\n".join(pm_edit.preview([pm_edit.SpeedFeed("TP1")]))


# --------------------------------------------------------------------------
# Отчёт макроса
# --------------------------------------------------------------------------
GOOD_REPORT = (
    "PM_EDIT_RESULT\n"
    "EDIT;Rough_D16;SpindleSpeed;4500;3000;4500;param\n"
    "EDIT;Rough_D16;Feedrate.Cutting;1200;900;900;command\n"
    "какая-то кракозябра из чужой кодировки\n")


def test_parse_result_reads_both_methods():
    results = pm_edit.parse_result(GOOD_REPORT)
    assert [r.param for r in results] == ["SpindleSpeed", "Feedrate.Cutting"]
    assert results[0].ok is True                      # 4500 из 4500
    assert results[1].ok is False                     # осталось 900 из 1200
    assert "параметр траектории" in results[0].method
    assert "команда" in results[1].method


def test_parse_result_ignores_broken_lines():
    assert pm_edit.parse_result("мусор\nEDIT;мало;полей\n") == []


def test_format_results_counts_and_reports():
    text = pm_edit.format_results(pm_edit.parse_result(GOOD_REPORT))
    assert "3000 → 4500" in text
    assert "записано 1 из 2" in text
    assert "подберём точную команду" in text


def test_format_results_without_data():
    assert "нет данных" in pm_edit.format_results([])


def test_last_results_without_file(tmp_path):
    results, note = pm_edit.last_results(tmp_path / "нет.txt")
    assert results == []
    assert "файла ещё нет" in note


def test_last_results_reads_file(tmp_path):
    path = tmp_path / "pm_edit_result.txt"
    path.write_text(GOOD_REPORT, encoding="utf-8")
    results, note = pm_edit.last_results(path)
    assert len(results) == 2
    assert "свежий файл" in note


# --------------------------------------------------------------------------
# Страховка: копия проекта
# --------------------------------------------------------------------------
def test_backup_project_makes_copy(tmp_path):
    project = tmp_path / "Деталь1"
    project.mkdir()
    (project / "Деталь1.pmlprj").write_text("проект", encoding="utf-8")

    copy = pm_edit.backup_project(project)

    assert copy.exists() and copy.is_dir()
    assert copy.name.startswith("Деталь1_AI_")
    assert (copy / "Деталь1.pmlprj").read_text(encoding="utf-8") == "проект"
    assert (project / "Деталь1.pmlprj").exists()      # оригинал на месте


def test_backup_project_two_copies_do_not_clash(tmp_path):
    project = tmp_path / "Деталь"
    project.mkdir()
    first = pm_edit.backup_project(project)
    second = pm_edit.backup_project(project)
    assert first != second


def test_backup_project_rejects_missing_folder(tmp_path):
    import pytest

    with pytest.raises(NotADirectoryError):
        pm_edit.backup_project(tmp_path / "нет такой папки")
