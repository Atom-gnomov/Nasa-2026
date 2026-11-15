"""Модель екіпажу й запасів (M24): потреби за біометрією, запаси з резервом, журнал розходу, попередження."""

import pytest

from app.core import crew
from app.core.crew import CrewMember


def test_reference_man_matches_nasa_energy_and_bvad_oxygen():
    needs = crew.daily_needs(crew.REFERENCE["male"])
    assert 2800 < needs["energy_kcal"] < 3400  # NASA-STD-3001: у середньому 3 035 ккал/добу
    assert needs["oxygen_kg"] == pytest.approx(0.895, rel=0.12)  # BVAD Table 3-31: 0,895 кг/добу
    assert needs["co2_kg"] > needs["oxygen_kg"]
    assert needs["food_kg"] == pytest.approx(2.39, rel=0.25)  # з упаковкою, ISS 2,39 кг
    assert needs["water_kg"] == pytest.approx(needs["energy_kcal"] / 1000.0)


def test_needs_grow_with_mass_height_and_activity_and_differ_by_sex():
    base = CrewMember("male", 80.0, 1.80, 35.0, "active")
    heavier = CrewMember("male", 95.0, 1.80, 35.0, "active")
    taller = CrewMember("male", 80.0, 1.95, 35.0, "active")
    lazy = CrewMember("male", 80.0, 1.80, 35.0, "sedentary")
    older = CrewMember("male", 80.0, 1.80, 55.0, "active")
    e = crew.energy_kcal
    assert e(heavier) > e(base) and e(taller) > e(base) and e(lazy) < e(base) and e(older) < e(base)
    twin = CrewMember("female", 80.0, 1.80, 35.0, "active")
    assert e(twin) != e(base)


def test_parse_member_fills_reference_values_and_validates():
    m = crew.parse_member({"sex": "female"})
    assert (m.mass_kg, m.height_m, m.age, m.activity) == (62.0, 1.65, 35.0, "active")
    for bad in ({}, {"sex": "x"}, {"sex": "male", "mass_kg": 5}, {"sex": "male", "activity": "z"},
                {"sex": "male", "bogus": 1}, {"sex": "male", "age": True}, "man"):
        with pytest.raises(ValueError):
            crew.parse_member(bad)


def test_supplies_default_to_recommended_reserve_and_scale_with_crew_and_days():
    one = crew.supplies_report([crew.REFERENCE["male"]], 10)
    two = crew.supplies_report([crew.REFERENCE["male"], crew.REFERENCE["male"]], 10)
    assert one["supply_days"] == pytest.approx(11.5) and not one["warnings"]
    assert two["loaded_total_kg"] == pytest.approx(2 * one["loaded_total_kg"])
    longer = crew.supplies_report([crew.REFERENCE["male"]], 20)
    assert longer["loaded_kg"]["oxygen"] == pytest.approx(2 * one["loaded_kg"]["oxygen"])
    assert one["required_kg"]["oxygen"] == pytest.approx(one["loaded_kg"]["oxygen"] / 1.15)


def test_warnings_for_low_reserve_and_shortage():
    m = [crew.REFERENCE["female"]]
    low = crew.supplies_report(m, 10, supply_days=10.5)
    assert [w["kind"] for w in low["warnings"]] == ["low_reserve"]
    short = crew.supplies_report(m, 10, supply_days=8)
    assert [w["kind"] for w in short["warnings"]] == ["shortage"]
    assert short["log"][-1]["worst"] == "shortage" and short["log"][-1]["remaining_pct"]["oxygen"] == 0.0


def test_log_counts_down_to_the_reserve():
    report = crew.supplies_report([crew.REFERENCE["male"]], 10)
    log = report["log"]
    assert log[0]["remaining_pct"] == {"oxygen": 100.0, "water": 100.0, "food": 100.0} and log[0]["worst"] == "ok"
    pcts = [e["remaining_pct"]["oxygen"] for e in log]
    assert pcts == sorted(pcts, reverse=True) and len(log) == 11
    assert log[-1]["day"] == 10 and log[-1]["remaining_pct"]["oxygen"] == pytest.approx(100 * 0.15 / 1.15, abs=0.2)
    assert log[-1]["worst"] in ("ok", "reserve")


def test_empty_crew_and_bad_days_are_rejected():
    with pytest.raises(ValueError):
        crew.supplies_report([], 10)
    with pytest.raises(ValueError):
        crew.supplies_report([crew.REFERENCE["male"]], 500)


def test_custom_supply_kg_overrides_days_per_resource_and_reports_balance():
    m = [crew.REFERENCE["male"]]
    base = crew.supplies_report(m, 10)
    need_o2 = base["required_kg"]["oxygen"]
    short = crew.supplies_report(m, 10, supply_kg={"oxygen": need_o2 * 0.5})
    o2 = short["resources"]["oxygen"]
    assert o2["custom"] and o2["loaded_kg"] == pytest.approx(need_o2 * 0.5)
    assert o2["runs_out_day"] == pytest.approx(5.0) and o2["deficit_kg"] == pytest.approx(need_o2 * 0.5)
    assert not short["resources"]["water"]["custom"] and short["resources"]["water"]["runs_out_day"] is None
    assert short["summary"]["mission_ok"] is False and short["summary"]["first_shortage_resource"] == "oxygen"
    assert short["summary"]["first_shortage_day"] == pytest.approx(5.0)
    assert [w["resource"] for w in short["warnings"]] == ["oxygen"] and short["warnings"][0]["kind"] == "shortage"
    assert short["log"][-1]["remaining_pct"]["oxygen"] == 0.0 and short["log"][-1]["status"]["oxygen"] == "shortage"
    assert short["log"][-1]["remaining_pct"]["water"] > 0.0


def test_excess_is_above_need_plus_reserve_and_economics_scales_with_price():
    m = [crew.REFERENCE["female"]]
    base = crew.supplies_report(m, 10)
    assert base["summary"]["excess_kg"] == pytest.approx(0.0) and base["summary"]["mission_ok"] is True
    big = crew.supplies_report(m, 10, supply_kg={"water": base["loaded_kg"]["water"] + 40.0})
    assert big["resources"]["water"]["excess_kg"] == pytest.approx(40.0)
    eco = crew.economics(big, (1000.0, 3000.0))
    assert eco["excess_usd"] == [pytest.approx(40_000.0), pytest.approx(120_000.0)]
    assert eco["deficit_usd"] == [0.0, 0.0] and eco["provisional"] is True
    assert eco["by_resource"]["water"]["excess_usd"][0] == pytest.approx(40_000.0)


def test_supply_kg_validation():
    m = [crew.REFERENCE["male"]]
    for bad in ({"air": 1}, {"oxygen": -1}, {"oxygen": True}, {"oxygen": "5"}, {"water": 1e9}, [1]):
        with pytest.raises(ValueError):
            crew.supplies_report(m, 10, supply_kg=bad)
    ok = crew.supplies_report(m, 10, supply_kg={"oxygen": None})  # null — не задано
    assert not ok["resources"]["oxygen"]["custom"]
