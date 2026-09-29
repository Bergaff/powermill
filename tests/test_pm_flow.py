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


# --------------------------------------------------------------------------
# Части операции: поток идёт по очереди и знает, где остановился
# --------------------------------------------------------------------------
def test_operation_parts_are_written_for_the_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(pm_flow, "OUTPUT_DIR", tmp_path)
    plan, _lines = pm_flow.build_plan(request())
    written = pm_flow.operation_parts(plan)
    keys = [part.key for part, _path in written]
    assert keys[:6] == ["tool", "block", "toolpath", "block_check", "feeds",
                        "calculate"]
    assert keys[6:] == ["block_size", "feeds_read", "computed"]   # чтения — в конце
    for _part, path in written:
        assert path.exists() and path.parent == tmp_path
        assert path.name.startswith("pm_flow_")


def test_every_part_has_its_own_timeout(tmp_path, monkeypatch):
    """У каждой части свой срок ожидания — окно шаблона и расчёт идут долго."""
    for create_tool in (True, False):
        keys = {part.key for part in pm_operation.build_parts(
            pm_flow.build_plan(request(tool_from_project=not create_tool))[0])}
        assert keys <= set(pm_flow.PART_TIMEOUTS), sorted(
            keys - set(pm_flow.PART_TIMEOUTS))
    assert pm_flow.PART_TIMEOUTS["calculate"] > pm_flow.PART_TIMEOUTS["block"]
    # части-проверки (чтения) не должны держать поток минутами
    assert pm_flow.PART_TIMEOUTS["computed"] <= 120


def test_wait_for_part_sees_the_step_in_the_report(tmp_path, monkeypatch):
    result = tmp_path / "result.txt"
    monkeypatch.setattr(pm_operation, "RESULT_FILE", result)
    part = pm_operation.MacroPart("block", "Заготовка", ("block",), [])
    result.write_text("STEP;tool;ok;фреза\n", encoding="utf-8")
    assert pm_flow.part_finished(part, result) is False
    assert pm_flow.wait_for_part(part, 0.0, result, timeout=0.2) is False

    result.write_text("STEP;tool;ok;фреза\nSTEP;block;ok;заготовка\n", encoding="utf-8")
    assert pm_flow.part_finished(part, result) is True
    assert pm_flow.wait_for_part(part, 0.0, result, timeout=1.0) is True
    # часть, которая сама написала «fail», поток обязан остановить
    result.write_text("STEP;block;fail;PowerMill не понял команду\n", encoding="utf-8")
    assert pm_flow.part_failure(part, result) == "Заготовка (Block): PowerMill не понял команду"


def test_stale_report_does_not_count_as_finished(tmp_path, monkeypatch):
    """Отчёт от прошлого запуска не должен выглядеть как «часть прошла»."""
    result = tmp_path / "result.txt"
    result.write_text("STEP;block;ok;прошлый раз\n", encoding="utf-8")
    old = result.stat().st_mtime - 600
    import os

    os.utime(result, (old, old))
    monkeypatch.setattr(pm_operation, "RESULT_FILE", result)
    part = pm_operation.MacroPart("block", "Заготовка", ("block",), [])
    # before — момент отправки части в PowerMill: отчёт старше него не считается
    assert pm_flow.wait_for_part(
        part, __import__("time").time(), result, timeout=0.2) is False


def test_flow_stops_and_names_the_failed_part():
    """Пункт 37 обязан сказать, НА КАКОЙ части встал, а не «что-то не так»."""
    text = Path(__file__).resolve().parent.parent.joinpath(
        "scripts", "make_flow.py").read_text(encoding="utf-8")
    assert "pm_flow.operation_parts(plan" in text
    assert "wait_for_part" in text
    assert "release_handles" in text                     # снятие залипших имён
    assert "не дошёл до конца части" in text
    assert "окно сообщений самого PowerMill" in text
    assert "остальное уцелеет" in text


def test_flow_explains_an_undefined_block_without_dying():
    """Не определилась заготовка — поток объясняет, что нажать, и спрашивает.

    Раньше это вылезало только на расчёте («заготовка не определена или
    содержит неподходящие значения») — после того, как человек ждал весь поток.
    """
    text = Path(__file__).resolve().parent.parent.joinpath(
        "scripts", "make_flow.py").read_text(encoding="utf-8")
    assert "part.verify" in text
    assert "Домой -> Заготовка -> «Вычислить» -> «Принять»" in text
    assert "Попробовать расчёт всё равно?" in text
    assert "continue" in text                     # можно пойти дальше по желанию


def test_preview_mentions_the_block_is_calculated_and_accepted():
    from src import pm_operation

    plan = pm_operation.OperationPlan(toolpath_name="C", tool_name="D16")
    text = "\n".join(pm_operation.preview(plan))
    assert "Заготовка" in text


# --------------------------------------------------------------------------
# ответы человека меняют план (а не только строчку в отчёте)
# --------------------------------------------------------------------------
def test_answers_rebuild_the_plan():
    """«Нет» на расчёт — значит НЕТ: план пересобирается по ответам.

    Раньше план строился до вопросов и не пересобирался: человек отвечал «нет»,
    поток всё равно считал траекторию, а в отчёте стояло «без расчёта».
    """
    req = request()
    assert req.calculate is True                      # по умолчанию считаем
    plan, lines = pm_flow.plan_with_answers(req, calculate=False,
                                            check_after=False, nc_after=False)
    assert req.calculate is False and plan.calculate is False
    assert req.check_after is False and req.nc_after is False
    assert any("Без расчёта" in line for line in lines)
    assert "Расчёт траектории — да" not in "\n".join(lines)


def test_no_means_no_in_the_script():
    """Сценарий обязан строить план ПОСЛЕ ответов, а не заранее."""
    script = Path(__file__).resolve().parent.parent.joinpath(
        "scripts", "make_flow.py").read_text(encoding="utf-8")
    assert "plan_with_answers" in script
    assert "pm_flow.build_plan(request)" not in script     # план не собирается до вопросов


def test_without_calculation_the_macro_does_not_calculate():
    req = request()
    plan, _lines = pm_flow.plan_with_answers(req, calculate=False,
                                             check_after=False, nc_after=False)
    text = pm_operation.build_macro(plan)
    assert 'EDIT TOOLPATH "Chernovaya_D16" CALCULATE' not in text
    assert "STEP;calculate;skip" in text              # часть честно пишет «пропущено»
    parts = pm_flow.operation_parts(plan, result_file=Path("/tmp/nonexistent.txt"))
    keys = [part.key for part, _path in parts]
    assert "computed" not in keys                     # проверять нечего — не считали


def test_warnings_after_answers_tell_about_disabled_calculation():
    req = request(allowance=0.3)
    before = pm_flow.warnings_for(req)
    assert not any("расчёт выключен" in item for item in before)
    pm_flow.plan_with_answers(req, calculate=False, check_after=True, nc_after=False)
    joined = " ".join(pm_flow.warnings_for(req))
    assert "расчёт выключен" in joined                # «нет» — и предупреждаем прямо
    assert "проверки без расчёта" in joined


# --------------------------------------------------------------------------
# имя траектории не должно быть занято (второй запуск на том же проекте)
# --------------------------------------------------------------------------
def test_free_toolpath_name_keeps_free_name():
    assert pm_flow.free_toolpath_name("Chernovaya_D16", []) == "Chernovaya_D16"
    assert pm_flow.free_toolpath_name("Chernovaya_D16",
                                      ["Chernovaya_D16_2"]) == "Chernovaya_D16"


def test_free_toolpath_name_adds_number_when_taken():
    assert pm_flow.free_toolpath_name("Chernovaya_D16",
                                      ["Chernovaya_D16"]) == "Chernovaya_D16_2"
    assert pm_flow.free_toolpath_name(
        "Chernovaya_D16", ["chernovaya_d16", "Chernovaya_D16_2"]) == "Chernovaya_D16_3"


def test_free_toolpath_name_handles_empty_name():
    assert pm_flow.free_toolpath_name("", []) == "Chernovaya_D16"
    assert pm_flow.free_toolpath_name("   ", ["Chernovaya_D16"]) == "Chernovaya_D16_2"


def test_script_checks_for_a_taken_toolpath_name():
    """Занятое имя траектории ловится ДО работы, а не падением на переименовании."""
    script = Path(__file__).resolve().parent.parent.joinpath(
        "scripts", "make_flow.py").read_text(encoding="utf-8")
    assert "live_toolpath_names" in script
    assert "free_toolpath_name" in script


def test_live_toolpath_names_without_powermill_is_empty():
    assert pm_flow.live_toolpath_names() == []      # в песочнице PowerMill нет


# --------------------------------------------------------------------------
# NC в потоке: без постпроцессора PowerMill файл не пишет
# --------------------------------------------------------------------------
def test_script_asks_for_the_postprocessor_before_nc():
    script = Path(__file__).resolve().parent.parent.joinpath(
        "scripts", "make_flow.py").read_text(encoding="utf-8")
    assert "pm_nc.saved_post()" in script
    assert "find_postprocessors" in script
    assert "NC пропущена: не задан постпроцессор" in script   # честно, а не падение
