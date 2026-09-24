"""
Тесты вывода NC-программы (шаг 3.5, пункт 36).

Здесь важно не «сделать вид, что NC готова», а честно проверить: макрос собран
из подтверждённых команд Autodesk, одноимённую программу не затираем молча, а в
отчёте всегда есть список «что не проверено».
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src import pm_nc, pml_vocab

VOCAB = pml_vocab.load_vocabulary()


def plan(**kwargs) -> pm_nc.NcPlan:
    data = {"name": "PROGRAM1", "toolpaths": ["Chernovaya_D16"], "number": 100}
    data.update(kwargs)
    return pm_nc.NcPlan(**data)


# --------------------------------------------------------------------------
# макрос
# --------------------------------------------------------------------------
def test_macro_uses_powermill_nc_commands():
    code = pm_nc.build_macro(plan())
    for command in ("CREATE NCPROGRAM 'PROGRAM1'",
                    "ACTIVATE NCPROGRAM 'PROGRAM1'",
                    "EDIT NCPROGRAM ; APPEND TOOLPATH 'Chernovaya_D16'",
                    "EDIT NCPROGRAM 'PROGRAM1' NUMBER 100",
                    "DEACTIVATE NCPROGRAM",
                    "ACTIVATE NCPROGRAM 'PROGRAM1' KEEP NCPROGRAM ;"):
        assert command in code, command


def test_macro_appends_toolpaths_in_plan_order():
    code = pm_nc.build_macro(plan(toolpaths=["B", "A", "C"]))
    positions = [code.index(f"APPEND TOOLPATH '{name}'") for name in ("B", "A", "C")]
    assert positions == sorted(positions)


def test_macro_checks_every_toolpath_exists():
    code = pm_nc.build_macro(plan(toolpaths=["A", "B"]))
    assert code.count("IF ENTITY_EXISTS('toolpath'") == 2
    assert "NC;append;fail;" in code


def test_macro_sets_filename_and_postprocessor():
    code = pm_nc.build_macro(plan(filename=Path("E:/nc/part.tap"),
                                  postprocessor=Path("E:/post/fanuc.pmoptz")))
    assert "EDIT NCPROGRAM 'PROGRAM1' FILENAME 'E:/nc/part.tap'" in code
    assert "EDIT NCPROGRAM 'PROGRAM1' TAPEOPTIONS 'E:/post/fanuc.pmoptz'" in code


def test_macro_refuses_to_overwrite_existing_program():
    """Одноимённую программу не затираем: пишем отказ и ничего не делаем."""
    code = pm_nc.build_macro(plan(), known_programs=["PROGRAM1"])
    assert "IF ENTITY_EXISTS('ncprogram', 'PROGRAM1')" in code
    assert "NC;exists;fail;" in code
    assert "DELETE NCPROGRAM" not in code


def test_macro_overwrites_when_allowed():
    code = pm_nc.build_macro(plan(overwrite=True), known_programs=["PROGRAM1"])
    assert "DELETE NCPROGRAM 'PROGRAM1'" in code
    assert "NC;exists;fail;" not in code


def test_macro_has_unique_file_handles_and_variables_only():
    code = pm_nc.build_macro(plan())
    handles = [line.split()[-1] for line in code.splitlines()
               if line.startswith("FILE OPEN")]
    assert len(handles) == len(set(handles))
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith(("//", ";")):
            continue
        for command in ("FILE WRITE", "PRINT", "MACRO PAUSE"):
            if stripped.startswith(command):
                assert stripped[len(command):].strip().startswith("$"), stripped


def test_macro_passes_own_validator():
    code = pm_nc.build_macro(plan(filename=Path("E:/nc/part.tap"),
                                  postprocessor=Path("E:/post/fanuc.pmoptz")),
                             known_programs=["OLD"])
    report = pml_vocab.validate(code, VOCAB)
    assert report["ok"], pml_vocab.format_check(report)


def test_write_macro_is_cp1251_with_crlf(tmp_path):
    path = pm_nc.write_macro(plan(), path=tmp_path / "pm_nc.mac")
    raw = path.read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
    assert "CREATE NCPROGRAM" in raw.decode("cp1251")


def test_preview_shows_paths_and_honesty():
    text = "\n".join(pm_nc.preview(plan(filename=Path("E:/nc/part.tap"))))
    assert "E:/nc/part.tap" in text.replace("\\", "/")
    assert "KEEP NCPROGRAM" in text


# --------------------------------------------------------------------------
# проверка плана и честный список
# --------------------------------------------------------------------------
def test_validate_plan_catches_problems(tmp_path):
    assert pm_nc.validate_plan(plan(toolpaths=[]))
    assert pm_nc.validate_plan(plan(name="   "))
    assert pm_nc.validate_plan(plan(number=0))
    assert pm_nc.validate_plan(plan(postprocessor=tmp_path / "нет.pmoptz"))
    assert pm_nc.validate_plan(plan(filename=Path("E:/nc/без_расширения")))
    assert pm_nc.validate_plan(plan()) == []


def test_validate_accepts_existing_postprocessor(tmp_path):
    post = tmp_path / "fanuc.pmoptz"
    post.write_text("post", encoding="utf-8")
    assert pm_nc.validate_plan(plan(postprocessor=post)) == []


def test_not_checked_always_mentions_machine_and_postprocessor():
    lines = "\n".join(pm_nc.not_checked_lines(plan()))
    assert "не прогонялся на станке" in lines
    assert "постпроцессор не задавали" in lines
    with_post = "\n".join(pm_nc.not_checked_lines(
        plan(postprocessor=Path("E:/post/fanuc.pmoptz"))))
    assert "fanuc.pmoptz" in with_post


# --------------------------------------------------------------------------
# разбор отчёта
# --------------------------------------------------------------------------
def test_parse_and_format_result():
    steps = pm_nc.parse_result(
        "NC;create;ok;PROGRAM1: программа создана\n"
        "NC;append;ok;Chernovaya_D16\n"
        "NC;write;ok;файл записан\n"
        "мусор\n")
    assert [s[0] for s in steps] == ["create", "append", "write"]
    formatted = pm_nc.format_result(steps)
    assert "Создание NC-программы" in formatted
    assert "Запись файла NC" in formatted


def test_last_result_reads_cp1251(tmp_path):
    file = tmp_path / "pm_nc_result.txt"
    file.write_bytes("NC;create;ok;Программа создана\n".encode("cp1251"))
    steps, _note = pm_nc.last_result(file)
    assert steps and steps[0][0] == "create"


def test_default_filename_uses_project_folder():
    path = pm_nc.default_filename(Path("E:/projects/Detal"), "PROGRAM1")
    assert path.name == "PROGRAM1.tap"
    assert "ncprograms" in path.parts


def test_find_postprocessors_scans_given_folder(tmp_path):
    (tmp_path / "fanuc.pmoptz").write_text("x", encoding="utf-8")
    (tmp_path / "siemens.pmoptz").write_text("x", encoding="utf-8")
    (tmp_path / "не_то.txt").write_text("x", encoding="utf-8")
    found = pm_nc.find_postprocessors(extra_dirs=[tmp_path])
    assert [p.name for p in found] == ["fanuc.pmoptz", "siemens.pmoptz"]


def test_find_postprocessors_missing_folder_is_safe(tmp_path):
    assert pm_nc.find_postprocessors(extra_dirs=[tmp_path / "нет_такой"]) == []
