"""Каталог сучасних ракет (app/data/rockets.json, задача D7): схема, зв'язки, джерела, значення.

Кожне число має джерело й дослівну цитату; тест фіксує ключові значення, щоб правка без нового джерела не пройшла
непомітно. Проєктні цілі не видаються за підтверджені польотом.
"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def _load():
    rockets = json.loads((ROOT / "app" / "data" / "rockets.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "contracts" / "schemas" / "rockets.schema.json").read_text(encoding="utf-8"))
    sites = json.loads((ROOT / "app" / "data" / "launch_sites.json").read_text(encoding="utf-8"))
    systems = json.loads((ROOT / "app" / "data" / "launch_systems.json").read_text(encoding="utf-8"))
    return rockets, schema, {s["id"]: s for s in sites}, {s["id"] for s in systems}


def _value(rocket, quantity):
    found = [f for f in rocket["facts"] if f["quantity"] == quantity]
    return found[0]["value"] if found else None


def test_matches_schema_and_ids_unique():
    rockets, schema, _, systems = _load()
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(rockets), key=str)
    assert not errors, [e.message for e in errors]
    ids = [r["id"] for r in rockets]
    assert len(ids) == len(set(ids))
    assert not set(ids) & systems, "ракета дублює систему запуску з launch_systems.json (D6)"


def test_launch_sites_exist_or_are_explained():
    rockets, _, sites, systems = _load()
    for r in rockets:
        for site_id in r["launch_site_ids"]:
            assert site_id in sites and sites[site_id]["kind"] == "spaceport", r["id"]
        if not r["launch_site_ids"]:
            assert r.get("site_note", "").strip(), f"{r['id']}: порожній список майданчиків без пояснення"
        if "launch_system_id" in r:
            assert r["launch_system_id"] in systems, r["id"]


def test_every_fact_has_a_source_and_the_number_is_in_the_quote():
    rockets, _, _, _ = _load()
    for r in rockets:
        assert r["status_note"].strip()
        for f in r["facts"]:
            where = f"{r['id']}/{f['quantity']}"
            assert f["source"]["url"].startswith("https://") and f["source"]["ref"].strip(), where
            if f["quantity"].startswith("capacity_"):
                assert isinstance(f["value"], (int, float)) and f["value"] > 0 and f["unit"] == "kg", where
                in_quote = f"{f['value']:,}" in f["quote"]
                assert in_quote or f.get("as_published", "") in f["quote"], where
            if f["source"]["kind"] == "secondary":
                assert f.get("note") or "Wikipedia" in r["status_note"], f"{where}: вторинне джерело без позначки"


def test_design_targets_are_not_presented_as_flown():
    rockets, _, _, _ = _load()
    for r in rockets:
        if r["status"] in ("design_target", "in_testing"):
            assert r["verified_by_flight"] is False, r["id"]
    by_status = {r["status"] for r in rockets}
    assert {"active", "design_target", "in_testing"} <= by_status


def test_tli_never_exceeds_leo():
    rockets, _, _, _ = _load()
    for r in rockets:
        tli, leo = _value(r, "capacity_tli_kg"), _value(r, "capacity_leo_kg")
        if tli and leo:
            assert tli < leo, r["id"]


@pytest.mark.parametrize(("rocket_id", "quantity", "value"), [
    ("falcon-9", "capacity_leo_kg", 22800),
    ("falcon-heavy", "capacity_leo_kg", 63800),
    ("starship", "capacity_leo_kg", 100000),
    ("starship", "price_usd_per_kg_lunar_surface", 100000),
    ("new-glenn", "capacity_leo_kg", 45000),
    ("new-glenn-9x4", "capacity_tli_kg", 20000),
    ("vulcan-vc2", "capacity_tli_kg", 6300),
    ("vulcan-vc4", "capacity_tli_kg", 9200),
    ("vulcan-vc6", "capacity_tli_kg", 11500),
    ("sls-block-1", "capacity_tli_kg", 27000),
    ("long-march-10", "capacity_tli_kg", 27000),
])
def test_published_values(rocket_id, quantity, value):
    rockets, _, _, _ = _load()
    rocket = next(r for r in rockets if r["id"] == rocket_id)
    assert _value(rocket, quantity) == value


def test_lower_bounds_are_marked():
    rockets, _, _, _ = _load()
    for rid, q in (("starship", "capacity_leo_kg"), ("sls-block-1", "capacity_tli_kg"),
                   ("long-march-10", "capacity_tli_kg"), ("new-glenn", "capacity_gto_kg")):
        rocket = next(r for r in rockets if r["id"] == rid)
        fact = next(f for f in rocket["facts"] if f["quantity"] == q)
        assert fact["bound"] == "at_least", (rid, q)
