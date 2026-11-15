"""Склад екіпажу за ролями й план підготовки (M27)."""

import json
from pathlib import Path

import pytest

from app.core import crew_roles
from tests.test_contracts import api_validator, assert_valid

APP_DATA = Path(__file__).resolve().parents[1] / "app" / "data"
DATA = json.loads((APP_DATA / "crew_roles.json").read_text("utf-8"))
CATALOG = json.loads((APP_DATA / "equipment_catalog.json").read_text("utf-8"))


def test_data_is_consistent():
    modules = {m["id"] for m in DATA["training_modules"]}
    for r in DATA["roles"]:
        assert set(r["training"]) <= modules
        assert 0 <= r["eva_share"] <= 1
    ids = {i["id"] for i in CATALOG["items"]}
    for preset in DATA["robotic_presets"]:
        assert {i["id"] for i in preset["items"]} <= ids


def test_composition_requires_roles_by_crew_size():
    assert crew_roles.composition(["commander"], DATA)["ok"]
    res = crew_roles.composition(["commander", "commander"], DATA)
    assert res["missing"] == ["pilot"] and not res["ok"]
    four = crew_roles.composition(["commander", "pilot", "scientist", "engineer"], DATA)
    assert four["ok"] and four["recommended"][0]["role"] == "physician"


def test_unknown_role_is_rejected():
    with pytest.raises(ValueError):
        crew_roles.composition(["janitor"], DATA)


def test_training_plan_sums_hours_and_shares_modules():
    plan = crew_roles.training_plan(["commander", "pilot"], DATA)
    assert plan["total_hours"] == sum(p["hours"] for p in plan["people"])
    shared = next(m for m in plan["modules"] if m["id"] == "basics")
    assert shared["people"] == 2


def test_crew_roles_endpoint(client):
    res = client.get("/api/crew-roles")
    assert res.status_code == 200
    assert_valid(api_validator("CrewRoles"), res.get_json())


def mission(client, members, **extra):
    return client.post("/api/mission", json={"crew_members": members, "days": 10, **extra})


def test_role_sets_default_activity_and_gives_crew_plan(client):
    res = mission(client, [{"sex": "male", "role": "scientist"}, {"sex": "female", "role": "commander"}])
    assert res.status_code == 200, res.get_json()
    data = res.get_json()
    assert_valid(api_validator("MissionResponse"), data)
    assert data["crew_supplies"]["members"][0]["activity"] == "very_active"
    assert data["crew_supplies"]["members"][1]["activity"] == "active"
    plan = data["crew_plan"]
    assert plan["missing"] == ["pilot"] and plan["training"]["total_hours"] > 0


def test_explicit_activity_wins_and_no_roles_means_no_plan(client):
    data = mission(client, [{"sex": "male", "role": "scientist", "activity": "low"}]).get_json()
    assert data["crew_supplies"]["members"][0]["activity"] == "low"
    assert mission(client, [{"sex": "male"}]).get_json()["crew_plan"] is None


def test_bad_role_is_400(client):
    assert mission(client, [{"sex": "male", "role": "janitor"}]).status_code == 400
