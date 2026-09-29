"""Тесты расчёта режимов резания (/cutting)."""
from __future__ import annotations

from src.cutting import (
    MATERIALS,
    answer,
    calculate,
    find_material,
    format_report,
    parse_request,
)


def test_find_material_aliases():
    assert find_material("Сталь 40Х, фреза D16").key == "40x"
    assert find_material("12Х18Н10Т").key == "12x18n10t"
    assert find_material("алюминий Д16Т").key == "d16t"
    assert find_material("чугун СЧ20").key == "sch20"
    assert find_material("полиамид капролон").key == "pom"
    assert find_material("что-то неизвестное") is None


def test_find_material_prefers_longest_alias():
    # «сталь 40х» длиннее, чем «40х», оба должны дать 40x
    assert find_material("сталь 40х").key == "40x"


def test_parse_request_extracts_parameters():
    req = parse_request("Сталь 40Х, фреза D16 z4 Sandvik, черновая")
    assert req["material"].key == "40x"
    assert req["diameter"] == 16
    assert req["flutes"] == 4
    assert req["tool"] == "end"
    assert req["op"] == "roughing"
    assert req["brand"] == "sandvik"


def test_parse_request_tool_and_op_detection():
    assert parse_request("Д16Т сферическая D8 чистовая")["tool"] == "ball"
    assert parse_request("Д16Т сферическая D8 чистовая")["op"] == "finishing"
    assert parse_request("сталь 20 торцевая D63")["tool"] == "face"
    assert parse_request("сталь 40Х сверло D8.5")["tool"] == "drill"
    assert parse_request("сталь 40Х сверло D8.5")["op"] == "drilling"
    assert parse_request("12Х18Н10Т фреза D10 hsm")["op"] == "hsm"


def test_parse_request_diameter_variants():
    assert parse_request("фреза d10 сталь 45")["diameter"] == 10
    assert parse_request("фреза Ф12 сталь 45")["diameter"] == 12
    assert parse_request("фреза D8.5 сталь 45")["diameter"] == 8.5


def test_parse_request_warns_without_material_and_diameter():
    req = parse_request("сделай что-нибудь")
    assert req["material"] is None
    assert req["warnings"]
    assert req["diameter"] == 12.0


def test_calculate_steel_40x_d16_roughing_is_sane():
    res = calculate(parse_request("Сталь 40Х, фреза D16, черновая"))
    assert 2000 <= res.rpm <= 4000
    assert 500 <= res.feed <= 1500
    assert 5 <= res.ap <= 16          # ap порядка 0.7·D
    assert 4 <= res.ae <= 9
    assert 1.0 <= res.power_kw <= 6.0
    assert "Offset Area Clearance" in res.strategy


def test_calculate_semi_finishing_reduces_load():
    rough = calculate(parse_request("Сталь 40Х фреза D16 черновая"))
    semi = calculate(parse_request("Сталь 40Х фреза D16 получистовая"))
    assert semi.feed < rough.feed
    assert semi.ap < rough.ap
    assert semi.ae < rough.ae


def test_hss_tool_is_slower_than_carbide():
    tc = calculate(parse_request("Сталь 45 фреза D10 черновая"))
    hss = calculate(parse_request("Сталь 45 фреза D10 черновая HSS Р6М5"))
    assert hss.rpm < tc.rpm
    assert hss.feed < tc.feed


def test_max_rpm_limit_is_respected_and_warned():
    res = calculate(parse_request("Д16Т фреза D6 макс 12000 черновая"))
    assert res.rpm <= 12000
    assert any("шпиндел" in w for w in res.warnings)


def test_spindle_power_warning():
    res = calculate(parse_request("чугун СЧ20 торцевая D100 5 кВт черновая"))
    assert any("мощност" in w for w in res.warnings)


def test_face_mill_depth_is_capped():
    res = calculate(parse_request("чугун СЧ20 торцевая D63"))
    assert res.ap <= 6.0
    assert res.ae > 30          # торцевая берёт широко


def test_drill_uses_depth_as_ap():
    res = calculate(parse_request("сталь 40Х сверло D8.5 глубина 30"))
    assert res.ap == 30.0
    assert res.ae == 8.5
    assert res.feed > 0


def test_ball_finishing_has_small_step():
    res = calculate(parse_request("Д16Т сферическая D8 чистовая"))
    assert res.ae <= 0.08 * 8 + 0.05
    assert res.ap <= 0.8


def test_all_materials_produce_positive_parameters():
    for mat in MATERIALS:
        res = calculate(parse_request(f"{mat.name} фреза D10 черновая"))
        assert res.rpm > 0 and res.feed > 0 and res.ap > 0 and res.ae > 0
        assert res.power_kw >= 0


def test_format_report_contains_key_fields():
    req = parse_request("Сталь 40Х фреза D16 черновая")
    text = format_report(req, calculate(req))
    for field in ("S (об/мин)", "F (мм/мин)", "ap (мм)", "ae (мм)", "Стратегия PowerMill"):
        assert field in text
    assert "проверить перед запуском" in text.lower()


def test_answer_returns_text_and_dict():
    text, data = answer("Сталь 40Х, фреза D16 Sandvik, черновая")
    assert "S (об/мин)" in text
    assert data["S_rpm"] > 0 and data["F_mm_min"] > 0
    assert data["strategy"]


def test_unknown_material_warns_about_default():
    _, _ = answer("какой-то сплав D10 черновая")
    req = parse_request("какой-то сплав D10 черновая")
    assert req["material"] is None
    res = calculate(req)
    assert "Сталь" in res.material_name
