"""Каталог обладнання NASA (П-14): дані, схема, суми за позиціями, /api/equipment-catalog, /api/mission."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from app.core import equipment, payload
from tests.test_contracts import api_validator, assert_valid

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "app" / "data" / "equipment_catalog.json").read_text(encoding="utf-8"))
CREW = [{"sex": "male"}, {"sex": "female"}]


def test_catalog_matches_schema_and_every_item_quotes_its_numbers():
    schema = json.loads((ROOT / "contracts" / "schemas" / "equipment_catalog.schema.json").read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema).iter_errors(CATALOG))
    assert not errors, errors[:2]
    for item in CATALOG["items"]:
        lo, hi = item["mass_kg"]
        assert 0 < lo <= hi
        # число з джерела має стояти в цитаті (діапазон, одиниця чи слово) — нічого не вигадано
        nums = (
            {f"{v:g}" for v in (lo, hi)}
            | {f"{v:,.0f}".replace(",", "") for v in (lo, hi)}
            | {f"{v:,.0f}" for v in (lo, hi)}
        )
        quote = item["source"]["quote"].replace(" ", "")
        assert any(n in quote or n in item["source"]["quote"] for n in nums), (item["id"], item["source"]["quote"])
        assert item["source"]["url"].startswith("https://") and item["source"]["kind"] == "primary"
    lo, hi = CATALOG["delivery_usd_per_kg"]
    assert 0 < lo <= hi and "per kg" in CATALOG["delivery_source"]["quote"]


def test_summarize_multiplies_by_count_and_prices_delivery():
    items = equipment.parse_items(
        [{"id": "clps_instrument", "count": 4}, {"id": "trident_drill", "count": 1}, {"id": "viper_rover", "count": 0}],
        CATALOG,
    )
    assert [(i["id"], c) for i, c in items] == [("clps_instrument", 4), ("trident_drill", 1)]
    s = equipment.summarize(items, CATALOG["delivery_usd_per_kg"])
    assert s["mass_range_kg"] == [pytest.approx(4 * 10 + 21.3), pytest.approx(4 * 15 + 21.3)]
    assert s["mass_kg"] == pytest.approx((s["mass_range_kg"][0] + s["mass_range_kg"][1]) / 2)
    assert s["power_w"] == pytest.approx(195.0) and s["supply_power_w"] == 0.0
    d_lo, d_hi = CATALOG["delivery_usd_per_kg"]
    assert s["delivery_usd"] == [
        pytest.approx(s["mass_range_kg"][0] * d_lo),
        pytest.approx(s["mass_range_kg"][1] * d_hi),
    ]


def test_parse_items_validation():
    for bad in (
        "x",
        [{"id": "nope"}],
        [{"id": "viper_rover", "count": -1}],
        [{"id": "viper_rover", "count": 1.5}],
        [{"id": "viper_rover"}, {"id": "viper_rover"}],
        [{"id": "viper_rover", "bogus": 1}],
        [1],
        [{"id": "viper_rover"}] * 13,
    ):
        with pytest.raises(ValueError):
            equipment.parse_items(bad, CATALOG)
    assert equipment.parse_items(None, CATALOG) == []


def test_category_kg_overrides_and_breakdown_adds_up():
    base = payload.payload_budget({"equipment": "basic"}, crew=2, days=10)
    assert {r["key"] for r in base.breakdown["life_support"]} == {"consumables", "fixed", "shield"}
    assert sum(r["kg"] for r in base.breakdown["life_support"]) == pytest.approx(base.masses_kg["life_support"])
    assert sum(r["kg"] for r in base.breakdown["comfort"]) == pytest.approx(base.masses_kg["comfort"])
    mine = payload.payload_budget(
        {"equipment": "basic"}, crew=2, days=10, category_kg={"equipment": 777.0, "comfort": 50.0}
    )
    assert mine.masses_kg["equipment"] == 777.0 and mine.masses_kg["comfort"] == 50.0
    assert mine.breakdown["equipment"] == [{"key": "custom", "kg": 777.0}]
    for bad in ({"x": 1}, {"equipment": -1}, {"equipment": True}, {"equipment": 1e9}, [1]):
        with pytest.raises(ValueError):
            payload.payload_budget(crew=2, days=1, category_kg=bad)
    with pytest.raises(ValueError):
        payload.payload_budget(crew=0, category_kg={"comfort": 10})


def test_power_source_cuts_panels_and_batteries():
    plain = payload.payload_budget(
        crew=2, days=10, longest_night_h=300, equipment={"mass_kg": 100.0, "power_w": 5000.0}
    )
    fed = payload.payload_budget(
        crew=2, days=10, longest_night_h=300, equipment={"mass_kg": 100.0, "power_w": 5000.0}, power_supply_w=1e9
    )
    assert fed.panel_kg == 0.0 and fed.battery_kg == 0.0 and plain.panel_kg > 0 and plain.battery_kg > 0
    assert fed.power_w == plain.power_w, "споживання те саме, змінюється лише чим його покривають"


def test_equipment_catalog_endpoint(client):
    res = client.get("/api/equipment-catalog")
    assert res.status_code == 200
    data = res.get_json()
    assert_valid(api_validator("EquipmentCatalog"), data)
    assert {i["id"] for i in data["items"]} == {i["id"] for i in CATALOG["items"]}
    ids = {p["id"] for p in data["parameters"]}
    assert {"oxygen_kg_per_person_day", "habitat_kg_per_m3", "equipment_mass_kg"} <= ids
    assert all(p["sources"] and p["range"] for p in data["parameters"])


def test_mission_with_catalog_items_and_category_kg(client):
    base = {"mission_profile": "crewed", "days": 10, "crew_members": CREW, "longest_night_h": 300}
    auto = client.post("/api/mission", json=base).get_json()
    assert auto["equipment"] is None
    picked = client.post(
        "/api/mission",
        json={**base, "equipment_items": [{"id": "viper_rover", "count": 2}, {"id": "fsp_reactor", "count": 1}]},
    )
    assert picked.status_code == 200, picked.get_json()
    data = picked.get_json()
    assert_valid(api_validator("MissionResponse"), data)
    eq = data["equipment"]
    assert eq["mass_kg"] == pytest.approx(2 * 475 + 6000) and eq["supply_power_w"] == 40000.0
    assert data["payload"]["masses_kg"]["equipment"] == pytest.approx(eq["mass_kg"])
    assert data["payload"]["breakdown"]["equipment"] == [{"key": "catalog_items", "kg": pytest.approx(eq["mass_kg"])}]
    assert eq["delivery_usd"][0] == pytest.approx(eq["mass_range_kg"][0] * 1_000_000)
    assert data["payload"]["battery_kg"] == 0.0, "реактор покриває споживання — акумулятори не потрібні"
    extra = client.post(
        "/api/mission",
        json={
            **base,
            "equipment_items": [{"id": "viper_rover", "count": 1}],
            "category_kg": {"equipment": 25, "life_support": 900},
        },
    ).get_json()
    assert extra["payload"]["masses_kg"]["equipment"] == pytest.approx(475 + 25)
    assert extra["payload"]["masses_kg"]["life_support"] == pytest.approx(900)
    assert {r["key"] for r in extra["payload"]["breakdown"]["equipment"]} == {"catalog_items", "extra"}


def test_mission_equipment_errors(client):
    base = {"mission_profile": "crewed", "days": 10, "crew_members": CREW}
    for bad in (
        {"equipment_items": [{"id": "nope"}]},
        {"equipment_items": "many"},
        {"category_kg": {"x": 1}},
        {"category_kg": {"comfort": -5}},
    ):
        assert client.post("/api/mission", json={**base, **bad}).status_code == 400, bad
    assert (
        client.post("/api/mission", json={"mission_profile": "uncrewed", "category_kg": {"comfort": 5}}).status_code
        == 400
    )
