"""Тесты шагов 3.2–3.3 — сборка черновой операции в проекте PowerMill (пункт 31).

Проверяем: команды из реальных макросов Autodesk, пробные слова инструмента
перебираются и попадают в отчёт, расчёт включается только по подтверждению.
"""
from __future__ import annotations

from src import pm_operation, pml_vocab

VOCAB = {"entities": ["model", "boundary", "tool", "toolpath", "workplane",
                      "ncprogram", "stockmodel", "pattern"], "parameters": []}

TEMPLATE = "3D-Area-Clearance/Model-Area-Clearance.003.ptf"


def make_plan(**kwargs) -> pm_operation.OperationPlan:
    base = dict(toolpath_name="Chernovaya_D16", tool_name="D16_Freza",
                tool_diameter=16.0, stepover=6.4, stepdown=8.0,
                rpm=4500, feed=1200, plunge=720)
    base.update(kwargs)
    return pm_operation.OperationPlan(**base)


# --------------------------------------------------------------------------
# Макрос
# --------------------------------------------------------------------------
def test_operation_macro_passes_validator():
    report = pml_vocab.validate(pm_operation.build_macro(make_plan()), VOCAB)
    assert report["ok"], pml_vocab.format_check(report)


def test_macro_resets_vars_and_writes_report():
    text = pm_operation.build_macro(make_plan())
    assert "RESET LOCALVARS" in text.splitlines()[:15]
    assert "FILE OPEN $pm_res FOR WRITE AS out" in text
    assert "FILE CLOSE out" in text
    assert "MESSAGE INFO" in text


def test_tool_creation_tries_words_and_reports():
    """DRILL подтверждён документацией, фрезу пробуем словами и смотрим отчёт."""
    text = pm_operation.build_macro(make_plan(create_tool=True))
    for word in pm_operation.END_MILL_WORDS:
        assert f"CREATE TOOL ; {word}" in text
    assert "STEP;tool_create;try;" in text
    assert "STRING($pm_tools1 != $pm_tools0)" in text      # выросло ли число
    assert "EDIT TOOL ; DIAMETER 16" in text
    assert "EDIT TOOL ; NUMBER COMMANDFROMUI 1" in text
    assert "RENAME Tool ; 'D16_Freza'" in text


def test_existing_tool_is_activated_not_created():
    text = pm_operation.build_macro(make_plan(create_tool=False))
    assert "ACTIVATE TOOL 'D16_Freza'" in text
    assert "CREATE TOOL" not in text


def test_block_is_reset_from_model():
    text = pm_operation.build_macro(make_plan())
    assert "EDIT TPPAGE SWBlock" in text
    assert "EDIT BLOCK COORDINATE WORLD" in text
    assert "EDIT BLOCK RESET" in text
    assert 'EDIT BLOCK RESETLIMIT "0.05"' in text
    assert "EDIT BLOCK ZMAX" not in text                 # верх не задавали


def test_block_z_max_when_asked():
    text = pm_operation.build_macro(make_plan(block_z_max=5.0))
    assert 'EDIT BLOCK ZMAX "5"' in text


def test_toolpath_imported_from_template_and_counted():
    text = pm_operation.build_macro(make_plan())
    assert (f'IMPORT TEMPLATE ENTITY TOOLPATH TMPLTSELECTORGUI "{TEMPLATE}"'
            in text)
    assert "INT $pm_tp_before = SIZE(folder('Toolpath'))" in text
    assert "INT $pm_tp_after = SIZE(folder('Toolpath'))" in text


def test_strategy_parameters_from_real_macros():
    text = pm_operation.build_macro(make_plan())
    assert "EDIT TPPAGE SWAreaClearance" in text
    assert "EDIT PAR 'CutDirection' 'any'" in text
    assert "EDIT PAR 'Tolerance' \"0.05\"" in text
    assert "EDIT PAR 'Thickness' \"0\"" in text
    assert "EDIT PAR 'Stepover' 6.4" in text
    assert "EDIT PAR 'AreaClearance.ZHeights.Stepdown' 8" in text
    assert "EDIT PAR 'CollisionCheck' '1'" in text


def test_stepover_stepdown_can_be_left_to_template():
    text = pm_operation.build_macro(make_plan(stepover=None, stepdown=None))
    assert "EDIT PAR 'Stepover'" not in text
    assert "AreaClearance.ZHeights.Stepdown" not in text


def test_z_limit_only_when_requested():
    without = pm_operation.build_macro(make_plan())
    assert "EDIT PAR 'ZRange.Minimum.Active' 0" in without
    assert "ZRange.Minimum.Value" not in without

    with_limit = pm_operation.build_macro(make_plan(z_min=-2.0))
    assert "EDIT PAR 'ZRange.Minimum.Active' 1" in with_limit
    assert "EDIT PAR 'ZRange.Minimum.Value' -2" in with_limit


def test_feeds_written_with_real_commands():
    text = pm_operation.build_macro(make_plan())
    assert "EDIT TPPAGE SWFeedSpeed" in text
    assert 'EDIT RPM "4500"' in text
    assert 'EDIT FRATE "1200"' in text
    assert 'EDIT PRATE "720"' in text


def test_calculate_only_when_confirmed():
    without = pm_operation.build_macro(make_plan(calculate=False))
    assert "STEP;calculate;skip" in without
    assert "CALCULATE" not in without.replace("CALCULATE_DIMENSIONS", "")

    with_calc = pm_operation.build_macro(make_plan(calculate=True))
    assert 'EDIT TOOLPATH "Chernovaya_D16" CALCULATE' in with_calc
    assert "STEP;calculate;ok" in with_calc


def test_rename_toolpath_uses_own_name():
    text = pm_operation.build_macro(make_plan())
    assert "RENAME TOOLPATH ; 'Chernovaya_D16'" in text


def test_write_macro_uses_windows_line_endings(tmp_path):
    path = pm_operation.write_macro(make_plan(), path=tmp_path / "op.mac",
                                    result_file=tmp_path / "res.txt")
    data = path.read_bytes()
    assert b"\r\n" in data
    assert b"\n" not in data.replace(b"\r\n", b"")
    assert b"END_MILL" in data


# --------------------------------------------------------------------------
# Предпросмотр и отчёт
# --------------------------------------------------------------------------
def test_preview_lists_every_step():
    text = "\n".join(pm_operation.preview(make_plan(calculate=True)))
    for expected in ("Инструмент", "Заготовка", "шаблона", "Параметры",
                     "Режимы", "расчёт ВКЛЮЧЁН"):
        assert expected in text


def test_parse_result_reads_steps():
    report = ("PM_OPERATION_RESULT\n"
              "STEP;tool;start;было инструментов: 0\n"
              "STEP;tool_create;try;END_MILL;1\n"
              "STEP;tool_create;True;1\n"
              "STEP;block;ok;100;50;20\n")
    steps = pm_operation.parse_result(report)
    assert [s[0] for s in steps] == ["tool", "tool_create", "tool_create", "block"]


def test_format_result_marks_failures_and_gives_advice():
    steps = [("tool_create", "fail", "ни одно слово не подошло"),
             ("block", "ok", "100;50;20")]
    text = pm_operation.format_result(steps)
    assert "✘ Создание инструмента: ни одно слово не подошло" in text
    assert "✔ Заготовка (Block): 100;50;20" in text
    assert "пришли этот отчёт" in text


def test_format_result_without_data():
    assert "пока нет" in pm_operation.format_result([])


def test_last_result_without_file(tmp_path):
    steps, note = pm_operation.last_result(tmp_path / "нет.txt")
    assert steps == []
    assert "файла ещё нет" in note


def test_skip_status_is_not_error():
    text = pm_operation.format_result([("calculate", "skip", "ты не подтверждал расчёт")])
    assert "•" in text
    assert "пришли этот отчёт" not in text
