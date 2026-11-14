"""Каталог систем запуску (app/data/launch_systems.json, задача D6): схема, зв'язки, джерела, значення.

Кожне число має джерело й дослівну цитату; тест фіксує значення, щоб правка без нового джерела не пройшла непомітно.
"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
FT_M = 0.3048  # міжнародний фут, точно
LB_KG = 0.45359237  # міжнародний фунт, точно


def _load():
    systems = json.loads((ROOT / "app" / "data" / "launch_systems.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "contracts" / "schemas" / "launch_systems.schema.json").read_text(encoding="utf-8"))
    sites = json.loads((ROOT / "app" / "data" / "launch_sites.json").read_text(encoding="utf-8"))
    return systems, schema, {s["id"]: s for s in sites}


def _facts(system, quantity):
    return [f for f in system["facts"] if f["quantity"] == quantity]


def test_matches_schema_and_ids_unique():
    systems, schema, _ = _load()
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(systems), key=str)
    assert not errors, [e.message for e in errors]
    ids = [s["id"] for s in systems]
    assert len(ids) == len(set(ids))


def test_launch_sites_exist_and_match_the_launch_kind():
    systems, _, sites = _load()
    for system in systems:
        for site_id in system["launch_site_ids"]:
            assert site_id in sites, f"{system['id']}: немає місця {site_id} у launch_sites.json"
            assert sites[site_id]["kind"] == system["kind"], system["id"]
        if system["kind"] == "air_launch":
            # повітряний старт — у межах дальності літака, а не з фіксованого місця
            assert system["launch_site_ids"] == [], system["id"]
        else:
            assert system["launch_site_ids"], system["id"]


def test_the_three_launch_kinds_of_proposal_p10_are_covered():
    systems, _, _ = _load()
    assert {s["kind"] for s in systems} == {"spaceport", "sea_platform", "air_launch"}
    assert any(s["active"] is True for s in systems) and any(s["active"] is False for s in systems)


def test_every_fact_has_a_source_and_a_quote():
    systems, _, _ = _load()
    for system in systems:
        assert system["status_note"].strip()
        for fact in system["facts"]:
            where = f"{system['id']}/{fact['quantity']}"
            assert fact["source"]["url"].startswith("https://") and fact["source"]["ref"].strip(), where
            assert len(fact["quote"]) >= 10, where
            if fact["quantity"].startswith(("capacity_", "drop_altitude")):
                assert isinstance(fact["value"], (int, float)) and fact.get("unit") in {"kg", "m"}, where
        if system["active"] is False:  # історична система: дата події в статусі
            assert any(ch.isdigit() for ch in system["status_note"]), system["id"]
        if system["active"] is None:  # невідомий стан не видаємо за відомий
            assert "не підтверджено" in system["status_note"], system["id"]


def test_air_launch_systems_describe_carrier_and_drop_altitude():
    systems, _, _ = _load()
    for system in (s for s in systems if s["kind"] == "air_launch"):
        assert _facts(system, "carrier_aircraft"), system["id"]
        assert _facts(system, "drop_altitude_m"), system["id"]


def test_unit_conversions_are_exact():
    systems, _, _ = _load()
    by_id = {s["id"]: s for s in systems}
    pegasus = by_id["pegasus-xl"]
    assert _facts(pegasus, "drop_altitude_m")[0]["value"] == pytest.approx(40_000 * FT_M, abs=0.5)  # «40 000 фт»
    assert _facts(pegasus, "capacity_leo_kg")[0]["value"] == pytest.approx(1000 * LB_KG, abs=0.01)  # «1 000 фунтів»


def _value(systems, system_id, quantity, condition_part=""):
    """Єдине значення факту за системою, величиною й підрядком умови."""
    system = next(s for s in systems if s["id"] == system_id)
    found = [f["value"] for f in _facts(system, quantity) if condition_part in f.get("condition", "")]
    assert len(found) == 1, (system_id, quantity, condition_part, found)
    return found[0]


def test_values_as_published():
    systems, _, _ = _load()

    def v(*args):
        return _value(systems, *args)

    assert v("pegasus-xl", "capacity_leo_kg") == 453.59  # Northrop Grumman: «1,000 pounds (453.59 kg)»
    assert v("launcherone", "capacity_leo_kg", "230 км") == 500
    assert v("launcherone", "capacity_sso_kg") == 300
    assert v("launcherone", "drop_altitude_m", "17 січня 2021") == 10_700
    # Ariane 6 User's Manual, Issue 2 Rev. 0, §2.4.2 (с. 35): СШО 500 км і полярна 900 км
    assert (v("ariane-62", "capacity_sso_kg"), v("ariane-62", "capacity_polar_kg")) == (7200, 7000)
    assert (v("ariane-64", "capacity_sso_kg"), v("ariane-64", "capacity_polar_kg")) == (15_500, 15_400)
    # ESA (сторінка 2013 року, орієнтовно): НОО й ГПО
    assert (v("ariane-62", "capacity_leo_kg"), v("ariane-62", "capacity_gto_kg")) == (10_300, 4500)
    assert (v("ariane-64", "capacity_leo_kg"), v("ariane-64", "capacity_gto_kg")) == (21_600, 11_500)
    sea = next(s for s in systems if s["id"] == "zenit-3sl-sea-launch")
    assert sorted(f["value"] for f in _facts(sea, "capacity_gto_kg")) == [5700, 6000], "обидва джерела — з роками"
    assert not _facts(sea, "capacity_leo_kg"), "для НОО Zenit-3SL у джерелах значення не знайдено — не вигадуємо"


def test_secondary_sources_are_labelled():
    """Довідкова стаття чи преса — secondary; лише документи виробника, оператора, агентства — primary."""
    systems, _, _ = _load()
    kinds = {(s["id"], f["source"]["kind"]) for s in systems for f in s["facts"]}
    assert ("launcherone", "secondary") in kinds and ("zenit-3sl-sea-launch", "secondary") in kinds
    assert ("pegasus-xl", "primary") in kinds and ("ariane-62", "primary") in kinds
    for system in systems:
        for fact in system["facts"]:
            if "wikipedia.org" in fact["source"]["url"] or "flightglobal.com" in fact["source"]["url"]:
                assert fact["source"]["kind"] == "secondary", (system["id"], fact["quantity"])


def test_operational_statuses_of_pegasus_and_ariane_64_are_backed_by_quoted_sources():
    """Останній політ Pegasus XL і перший політ Ariane 64 — з цитатами; «останній політ» не видаємо за підтверджений."""
    systems, _, _ = _load()
    by_id = {s["id"]: s for s in systems}
    pegasus = by_id["pegasus-xl"]
    last = _facts(pegasus, "last_flight")
    assert [f["value"] for f in last] == ["2026-07-03"]
    assert last[0]["source"]["kind"] == "primary" and "Marshall Islands Time" in last[0]["quote"]
    flights = {f["value"]: f for f in _facts(pegasus, "flights")}
    assert sorted(flights) == [45, 46], "до польоту 3 липня 2026 і після нього — окремі факти з умовою"
    assert all(f.get("condition") for f in flights.values())
    # прямо сказано, що «останній політ» не підтверджено первинними джерелами
    assert "не містять" in pegasus["status_note"]

    ariane64 = by_id["ariane-64"]
    first = _facts(ariane64, "first_flight")
    assert len(first) == 2 and {f["value"] for f in first} == {"2026-02-12"}
    assert all(f["source"]["kind"] == "primary" for f in first)
    assert any("first Ariane 64" in f["quote"] for f in first)
    assert any("first flight of Ariane 64" in f["quote"] for f in first)
    assert ariane64["active"] is True
