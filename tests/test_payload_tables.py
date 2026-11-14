"""Таблиці корисного навантаження з джерел NASA (app/data/payload_tables.json, задача D4).

Тести фіксують значення й обчислення, щоб правка числа без нового джерела не пройшла непомітно, і звіряють
model_value з тимчасовими коефіцієнтами в app/core — якщо модель змінять, таблицю треба оновити.
"""

import json
from dataclasses import fields
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from app.core import cost, payload

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def data():
    return json.loads((ROOT / "app" / "data" / "payload_tables.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def params(data):
    return {p["id"]: p for p in data["parameters"]}


def _fact(param, quantity):
    found = [f for f in param["facts"] if f["quantity"] == quantity]
    assert len(found) == 1, quantity
    return found[0]


def test_matches_schema_and_ids_unique(data):
    schema = json.loads((ROOT / "contracts" / "schemas" / "payload_tables.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.path))
    assert not errors, [f"{list(e.path)}: {e.message}" for e in errors[:5]]
    ids = [p["id"] for p in data["parameters"]]
    assert len(ids) == len(set(ids))


def test_every_number_comes_from_nasa_with_a_quote(params):
    for p in params.values():
        if p["range"] is not None:
            assert p["range"][0] <= p["range"][1], p["id"]
        for f in p["facts"]:
            src = f["source"]
            assert src["kind"] == "primary", (p["id"], f["quantity"])
            assert src["url"].startswith(("https://ntrs.nasa.gov/", "https://www.nasa.gov/", "https://oig.nasa.gov/"))
            assert "с." in src["ref"], "сторінка обов'язкова"


def test_model_value_mirrors_the_current_provisional_coefficients(params):
    """Порівняння «тимчасове ↔ джерело» має сенс лише поки model_value збігається з кодом."""
    objects = {"PayloadParams": payload.DEFAULT_PARAMS, "CostTable": cost.CostTable()}
    for p in params.values():
        if "model_param" not in p:
            continue
        cls, name = p["model_param"].split(".")
        assert name in {f.name for f in fields(objects[cls])}, p["model_param"]
        current = getattr(objects[cls], name)
        expected = list(current) if isinstance(current, tuple) else current
        assert p["model_value"] == pytest.approx(expected), f"{p['model_param']} змінено в коді — оновіть таблицю D4"


def test_values_as_published(params):
    assert params["food_kg_per_person_day"]["range"] == [1.83, 2.39]
    assert _fact(params["oxygen_kg_per_person_day"], "oxygen_consumed")["value"] == 0.895
    assert params["habitable_volume_m3_per_person"]["range"] == [25.0, 28.96]
    assert params["habitat_kg_per_m3"]["range"] == [9.16, 137.3]
    assert params["battery_depth_of_discharge"]["range"] == [0.6, 0.6]
    assert params["lunar_delivery_usd_per_kg"]["range"] == [1.0e6, 1.2e6]
    assert params["iss_cargo_usd_per_kg"]["range"] == [63200.0, 71800.0]
    assert params["equipment_mass_kg"]["range"] == [10.0, 475.0]
    assert "25 m3 (883 ft3)" in _fact(params["habitable_volume_m3_per_person"], "minimum_net_habitable_volume")["quote"]


def test_derived_values_follow_from_the_facts(params):
    # витратні: відкритий цикл = їжа з упаковкою + кисень + вода ранньої планетної бази; регенерація = лише їжа
    food = params["food_kg_per_person_day"]["range"][1]
    oxygen = _fact(params["oxygen_kg_per_person_day"], "oxygen_consumed")["value"]
    water_early_base = 4.48
    assert "4.48" in _fact(params["water_kg_per_person_day"], "total_water_consumption")["quote"]
    lo, hi = params["consumables_kg_per_person_day"]["range"]
    assert lo == food and hi == pytest.approx(food + oxygen + water_early_base, abs=0.005)
    # сонячні батареї: Вт/кг = 1000 / (кг/кВт)
    assert params["solar_array_w_per_kg"]["range"] == pytest.approx([1000 / 54, 1000 / 20], abs=0.05)
    # акумулятор із корпусом: 1000 / 5,9 кг/кВт·год ≈ 169 Вт·год/кг — у межах діапазону
    wh = 1000 / _fact(params["battery_wh_per_kg"], "li_ion_storage_with_enclosure")["value"]
    lo, hi = params["battery_wh_per_kg"]["range"]
    assert lo <= wh <= hi
    # обладнання VIPER: вартість життєвого циклу / маса
    usd = _fact(params["equipment_usd_per_kg"], "viper_life_cycle_cost")["value"] * 1e6
    kg = _fact(params["equipment_usd_per_kg"], "viper_delivered_mass")["value"]
    assert params["equipment_usd_per_kg"]["range"][0] == pytest.approx(usd / kg, abs=1)


def test_gaps_are_explicit_not_invented(params):
    """Те, чого в джерелах NASA не знайдено, позначено no_source без чисел — а не заповнено здогадкою."""
    gaps = {p["id"] for p in params.values() if p["status"] == "no_source"}
    assert {"structure_fraction", "margin_fraction", "ls_shield_kg"} <= gaps
    for gap in gaps:
        assert params[gap]["range"] is None and not params[gap]["facts"]
