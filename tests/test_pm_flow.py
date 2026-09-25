"""
Тесты потока «сказал: делай» (шаг 3.6, пункт 37).

Поток связывает уже проверенные куски (пункты 31, 35, 36), поэтому проверяем:
план считается и понятно печатается, предупреждения честные, отчёт собирается из
всех шагов и всегда содержит «что не проверено».
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src import pm_check, pm_flow, pm_nc, pm_operation, pml_vocab


def request(**kwargs) -> pm_flow.FlowRequest:
    data = {"material": "Сталь 40Х", "tool_name": "D16_Freza", "tool_diameter": 16.0,
            "toolpath_name": "Chernovaya_D16"}
    data.update(kwargs)
    return pm_flow.FlowRequest(**data)


# --------------------------------------------------------------------------
# план
# --------------------------------------------------------------------------
def test_build_plan_uses_cutting_calculator():
    plan, lines = pm_flow.build_plan(request())
    assert isinstance(plan, pm_operation.OperationPlan)
    assert plan.rpm and plan.feed and plan.plunge          # режимы посчитаны
    assert plan.stepover and plan.stepdown                 # шаг и заглубление из расчёта
    assert plan.calculate is True
    text = "\n".join(lines)
    assert "Сталь 40Х" not in text or "Режимы посчитаны" in text
    assert "Заготовка" in text and "Траектория из шаблона" in text


def test_build_plan_respects_manual_numbers():
    plan, _lines = pm_flow.build_plan(request(stepover=7.5, stepdown=3.0,
                                              allowance=0.3, tool_from_project=True))
    assert plan.stepover == 7.5 and plan.stepdown == 3.0
    assert plan.thickness == 0.3
    assert plan.create_tool is False


def test_build_plan_without_calculation():
    plan, lines = pm_flow.build_plan(request(calculate=False))
    assert plan.calculate is False
    assert any("Без расчёта" in line for line in lines)


def test_plan_lists_checks_and_nc_when_asked():
    _plan, lines = pm_flow.build_plan(request(check_after=True, nc_after=True))
    text = "\n".join(lines)
    assert "проверки" in text.lower()
    assert "NC-программа" in text


def test_plan_is_valid_for_operation_macro():
    """План потока должен давать корректный макрос операции (проверка словарём)."""
    plan, _lines = pm_flow.build_plan(request())
    code = pm_operation.build_macro(plan)
    report = pml_vocab.validate(code, pml_vocab.load_vocabulary())
    assert report["ok"], pml_vocab.format_check(report)


# --------------------------------------------------------------------------
# предупреждения
# --------------------------------------------------------------------------
def test_warnings_flag_zero_allowance():
    items = "\n".join(pm_flow.warnings_for(request(allowance=0)))
    assert "припуск на чистовую 0 мм" in items


def test_warnings_flag_stepover_bigger_than_tool():
    items = "\n".join(pm_flow.warnings_for(request(stepover=25, tool_diameter=16)))
    assert "больше диаметра фрезы" in items


def test_warnings_flag_checks_without_calculation():
    items = "\n".join(pm_flow.warnings_for(request(calculate=False, check_after=True)))
    assert "проверки без расчёта" in items.lower()
    assert "расчёт выключен" in items


def test_warnings_empty_for_sane_request():
    assert pm_flow.warnings_for(request(allowance=0.3, stepover=8)) == []


# --------------------------------------------------------------------------
# отчёт
# --------------------------------------------------------------------------
def test_report_contains_steps_checks_and_nc():
    report = pm_flow.FlowReport(request=request(check_after=True, nc_after=True))
    report.add("Операция: Инструмент", "ok", "фреза создана")
    report.add("Операция: Расчёт траектории", "ok", "посчитана")
    report.check_steps = pm_check.parse_result(
        "CHK;exists;ok;Черновая\n"
        "CHK;safety;safe;статус при резании: safe\n")
    report.nc_steps = pm_nc.parse_result("NC;write;ok;файл записан\n")
    report.finished = True

    text = report.format()
    assert "Что сделано:" in text
    assert "фреза создана" in text
    assert "Проверки после расчёта" in text
    assert "NC-программа" in text
    assert "не прогонялся на станке" in text        # честность по NC
    assert "поток доведён до конца" in text
    assert "не заменяет пробный прогон" in text


def test_report_shows_failures_and_warnings():
    report = pm_flow.FlowReport(request=request())
    report.add("Операция: Расчёт траектории", "fail", "PowerMill не принял команду")
    report.warnings.append("смотри строки с ✘")
    text = report.format()
    assert "✘" in text
    assert "поток остановлен" in text
    assert "смотри строки с ✘" in text


def test_report_without_checks_is_quiet():
    report = pm_flow.FlowReport(request=request(check_after=False, nc_after=False))
    report.add("Операция: Инструмент", "ok", "ок")
    text = report.format()
    assert "Проверки после расчёта" not in text
    assert "NC-программа (пункт 36)" not in text


def test_save_report_writes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(pm_flow, "REPORT_FILE", tmp_path / "pm_flow_report.txt")
    report = pm_flow.FlowReport(request=request())
    report.add("Операция", "ok", "готово")
    path = pm_flow.save_report(report)
    assert path.exists()
    assert "шаг 3.6" in path.read_text(encoding="utf-8")
    assert pm_flow.report_path() == path


# --------------------------------------------------------------------------
# вспомогательные функции
# --------------------------------------------------------------------------
def test_backup_without_folder_is_none():
    assert pm_flow.backup(None) is None
    assert pm_flow.backup("") is None


def test_backup_copies_project(tmp_path, monkeypatch):
    from src import pm_edit

    monkeypatch.setattr(pm_edit, "backup_project",
                        lambda folder, stamp=None: Path(folder) / "Detal_AI_20260924_1310")
    copy = pm_flow.backup(tmp_path)
    assert copy is not None and "AI" in str(copy)


def test_operation_macro_written(tmp_path, monkeypatch):
    monkeypatch.setattr(pm_flow, "FLOW_MACRO", tmp_path / "pm_flow.mac")
    plan, _lines = pm_flow.build_plan(request())
    path = pm_flow.operation_macro(plan)
    assert path.exists()
    raw = path.read_bytes()
    assert b"\r\n" in raw and "RESET LOCALVARS" in raw.decode("cp1251")


def test_summarize_operation_reuses_point31_format():
    steps = pm_operation.parse_result("STEP;tool;ok;фреза создана\n")
    text = "\n".join(pm_flow.summarize_operation(steps))
    assert "Инструмент" in text
