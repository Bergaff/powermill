"""
Тесты проверок траекторий (шаг 3.4, пункт 35).

PowerMill здесь не нужен: проверяем сам макрос (штатные команды EDIT COLLISION и
чтение свойств траектории), разбор его отчёта и честный итог — в том числе
случай «макрос остановился, статус прочитать не удалось».
"""
from __future__ import annotations

import pytest

from src import pm_check, pml_vocab

VOCAB = pml_vocab.load_vocabulary()


def plan(**kwargs) -> pm_check.CheckPlan:
    data = {"toolpaths": ["Chernovaya_D16"]}
    data.update(kwargs)
    return pm_check.CheckPlan(**data)


# --------------------------------------------------------------------------
# макрос
# --------------------------------------------------------------------------
def test_macro_uses_powermill_collision_commands():
    """Команды проверок — из рабочего макроса Autodesk, не придуманные."""
    code = pm_check.build_macro(plan())
    for command in ("EDIT COLLISION TYPE GOUGE", "EDIT COLLISION APPLY",
                    "EDIT COLLISION TYPE COLLISION",
                    "EDIT COLLISION SHANK_CLEARANCE",
                    "EDIT COLLISION HOLDER_CLEARANCE",
                    "EDIT COLLISION SPLIT_TOOLPATH Y",
                    "EDIT COLLISION DEPTH Y",
                    "EDIT COLLISION ADJUST_TOOL Y"):
        assert command in code, command


def test_macro_reads_statuses_from_toolpath_properties():
    code = pm_check.build_macro(plan())
    assert "$pm_tp_1.Computed" in code
    assert "$pm_tp_1.Verification.CollisionChecked" in code
    assert "$pm_tp_1.Verification.GougeChecked" in code
    assert "$pm_tp_1.Safety.Tool.Cutting.Status" in code


def test_macro_activates_toolpath_before_checks():
    """EDIT COLLISION действует на активную траекторию — её надо активировать."""
    code = pm_check.build_macro(plan())
    assert "ACTIVATE TOOLPATH 'Chernovaya_D16'" in code
    assert code.index("ACTIVATE TOOLPATH") < code.index("EDIT COLLISION TYPE GOUGE")


def test_macro_writes_report_lines_and_trace_files():
    code = pm_check.build_macro(plan())
    for marker in ("CHK;exists;", "CHK;calculate;", "CHK;gouge;",
                   "CHK;collision;", "CHK;verify;", "CHK;safety;"):
        assert marker in code, marker
    for path in pm_check.trace_files():
        assert str(path).replace("\\", "/") in code


def test_macro_handles_missing_toolpath():
    code = pm_check.build_macro(plan())
    assert "IF NOT ENTITY_EXISTS('toolpath', 'Chernovaya_D16')" in code
    assert "CHK;exists;fail;" in code


def test_macro_skips_disabled_checks():
    code = pm_check.build_macro(plan(gouge=False, collision=False))
    assert "EDIT COLLISION TYPE GOUGE" not in code
    assert "EDIT COLLISION TYPE COLLISION" not in code
    assert "CHK;gouge;skip;" in code and "CHK;collision;skip;" in code


def test_macro_without_status_reading():
    code = pm_check.build_macro(plan(read_status=False))
    assert "Safety.Tool.Cutting.Status" not in code


def test_macro_recalcs_only_when_allowed():
    assert "EDIT TOOLPATH 'Chernovaya_D16' CALCULATE" in pm_check.build_macro(plan())
    assert "EDIT TOOLPATH" not in pm_check.build_macro(plan(recalc=False))


def test_macro_declares_each_variable_once():
    """Объявления — на верхнем уровне: внутри IF/ELSE только присваивание.

    Иначе PowerMill отвечает «local variable is already defined» — на этом уже
    спотыкались, поэтому проверяем и повторные объявления, и объявления в блоках.
    """
    import re

    code = pm_check.build_macro(plan(toolpaths=["A", "B"]))
    declared = re.findall(r"\b(?:STRING|ENTITY|INT|BOOL|REAL)\s+(\$[A-Za-z0-9_]+)", code)
    assert len(declared) == len(set(declared)), declared

    depth = 0
    for line in code.splitlines():
        if depth > 0 and line.strip().startswith("STRING $"):
            # внутри блока допускается объявление только сущности траектории
            assert "ENTITY $pm_tp_" in line, line
        depth += line.count("{") - line.count("}")


def test_macro_has_unique_file_handles():
    code = pm_check.build_macro(plan(toolpaths=["A", "B"]))
    handles = [line.split()[-1] for line in code.splitlines()
               if line.startswith("FILE OPEN")]
    assert len(handles) == len(set(handles)), handles


def test_macro_has_no_command_concatenation_or_literals():
    """Живое правило PowerMill: в FILE WRITE/PRINT — только переменные."""
    code = pm_check.build_macro(plan())
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith(("//", ";")):
            continue
        for command in ("FILE WRITE", "PRINT", "MACRO PAUSE"):
            if stripped.startswith(command):
                assert stripped[len(command):].strip().startswith("$"), stripped


def test_macro_passes_own_validator():
    report = pml_vocab.validate(pm_check.build_macro(plan()), VOCAB)
    assert report["ok"], pml_vocab.format_check(report)


def test_write_macro_is_cp1251_with_crlf(tmp_path):
    path = pm_check.write_macro(plan(), path=tmp_path / "pm_check.mac")
    raw = path.read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
    assert "EDIT COLLISION" in raw.decode("cp1251")


# --------------------------------------------------------------------------
# план и его проверка
# --------------------------------------------------------------------------
def test_validate_plan_catches_problems():
    assert pm_check.validate_plan(plan(toolpaths=[]))
    assert pm_check.validate_plan(plan(toolpaths=[" Chernovaya"]))
    assert pm_check.validate_plan(plan(holder_clearance=-1))
    assert pm_check.validate_plan(plan(gouge=False, collision=False, read_status=False))
    assert pm_check.validate_plan(plan()) == []


def test_preview_lists_commands():
    text = "\n".join(pm_check.preview(plan()))
    assert "EDIT COLLISION TYPE GOUGE" in text
    assert "зазор хвостовика" in text.lower() or "хвостовика" in text.lower()
    assert "Safety.Tool.Cutting.Status" in text


# --------------------------------------------------------------------------
# разбор отчёта и итог
# --------------------------------------------------------------------------
def test_parse_result_and_format():
    text = ("CHK;exists;ok;Черновая\n"
            "CHK;gouge;ok;Черновая: зарезы проверены\n"
            "мусор\n")
    steps = pm_check.parse_result(text)
    assert [s[0] for s in steps] == ["exists", "gouge"]
    formatted = pm_check.format_result(steps)
    assert "Траектория в проекте" in formatted
    assert "✔" in formatted


def test_summarize_all_clean():
    steps = pm_check.parse_result(
        "CHK;exists;ok;Черновая\n"
        "CHK;calculate;ok;Черновая: досчитана\n"
        "CHK;gouge;ok;зарезы проверены\n"
        "CHK;collision;ok;столкновения проверены\n"
        "CHK;verify;ok;столкновения проверены=yes, зарезы проверены=yes\n"
        "CHK;safety;safe;статус при резании: safe\n")
    ok, lines = pm_check.summarize(steps)
    assert ok is True
    assert any("ИТОГ: замечаний от PowerMill нет" in line for line in lines)


def test_summarize_finds_collisions():
    steps = pm_check.parse_result(
        "CHK;exists;ok;Черновая\n"
        "CHK;safety;collides;статус при резании: collides\n")
    ok, lines = pm_check.summarize(steps)
    assert ok is False
    assert any("✘" in line and "collides" in line for line in lines)


def test_summarize_lists_what_was_not_checked():
    steps = pm_check.parse_result(
        "CHK;gouge;skip;проверка зарезов выключена\n"
        "CHK;collision;skip;проверка столкновений выключена\n")
    ok, lines = pm_check.summarize(steps)
    assert ok is True
    assert any("Не проверено" in line for line in lines)


def test_summarize_missing_toolpath_is_problem():
    steps = pm_check.parse_result("CHK;exists;fail;Chernovaya: нет в проекте\n")
    ok, lines = pm_check.summarize(steps)
    assert ok is False
    assert any("нет в проекте" in line for line in lines)


def test_summarize_empty_report_is_honest():
    ok, lines = pm_check.summarize([])
    assert ok is False
    assert any("Отчёта проверок нет" in line for line in lines)


def test_classify_safety():
    assert pm_check.classify_safety("safe") == "ok"
    assert pm_check.classify_safety("Collides") == "bad"
    assert pm_check.classify_safety("gouge detected") == "bad"
    assert pm_check.classify_safety("") == "unknown"
    assert pm_check.classify_safety("странное_слово") == "unknown"


def test_last_result_and_missing_traces(tmp_path, monkeypatch):
    result = tmp_path / "res.txt"
    monkeypatch.setattr(pm_check, "trace_files",
                        lambda: [tmp_path / "t1.txt", tmp_path / "t2.txt"])
    steps, note = pm_check.last_result(result)
    assert steps == [] and "файла ещё нет" in note

    result.write_text("CHK;exists;ok;A\n", encoding="cp1251")
    steps, _note = pm_check.last_result(result)
    assert steps and steps[0][2] == "A"

    (tmp_path / "t1.txt").write_text("шаг", encoding="utf-8")
    assert [p.name for p in pm_check.missing_traces()] == ["t2.txt"]


def test_result_paths_for_reports():
    paths = pm_check.result_paths()
    assert paths["macro"].name == "pm_check.mac"
    assert paths["result"].name == "pm_check_result.txt"
