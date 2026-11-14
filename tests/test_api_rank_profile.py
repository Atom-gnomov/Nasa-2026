"""POST /api/rank з профілем місії (задача B13): пріоритети й вимоги з профілю, явні значення переважають."""

import json
from pathlib import Path

import pytest

from tests.test_contracts import api_validator, assert_valid

pytest.importorskip("naif_de440")

PERIOD = {"start": "2027-01-01T00:00:00Z", "end": "2027-01-30T00:00:00Z"}
POINTS = [{"site_id": "apollo-11"}, {"lat": -89.5, "lon": 0.0, "name": "Південний полюс"}]
THRESHOLDS = json.loads(
    (Path(__file__).resolve().parents[1] / "app" / "data" / "mission_thresholds.json").read_text(encoding="utf-8"))


def rank(client, **extra):
    return client.post("/api/rank", json={"points": POINTS, **PERIOD, **extra})


def test_without_profile_nothing_changes(client):
    data = rank(client).get_json()
    assert data["profile"] is None
    assert data["priorities"] == ["energy", "comms"]


def test_uncrewed_profile_keeps_default_priorities_and_matches_contract(client):
    res = rank(client, mission_profile="uncrewed")
    assert res.status_code == 200
    data = res.get_json()
    assert_valid(api_validator("RankResponse"), data)
    assert data["priorities"] == ["energy", "comms"]
    assert data["profile"]["profile"] == "uncrewed" and data["profile"]["crew"] == 0
    assert data["profile"]["limits"] == {}


def test_crewed_profile_sets_priorities_requirements_and_reports_what_it_set(client):
    res = rank(client, mission_profile="crewed", crew=3)
    assert res.status_code == 200
    data = res.get_json()
    assert_valid(api_validator("RankResponse"), data)
    assert data["priorities"][0] == "radiation"
    profile = data["profile"]
    assert profile["crew"] == 3 and "priorities" in profile["from_profile"]
    assert profile["limits"]["landing_slope_deg"]["id"] == "landing-slope-100m"
    sun_row = next(r for r in THRESHOLDS if r["quantity"] == "sun_visible_fraction")
    hours = sun_row["value"] / 100.0 * data["period"]["period_h"]
    # вимога профілю застосована: точка з меншою кількістю годин Сонця недопустима
    for item in data["ranking"]:
        assert item["feasible"] == (item["summary"]["sun_hours"] >= hours - 1e-9)


def test_explicit_priorities_and_requirements_win_over_the_profile(client):
    res = rank(client, mission_profile="crewed", crew=2, priorities=["comms", "energy"],
               requirements={"min_sun_hours": 0})
    data = res.get_json()
    assert data["priorities"] == ["comms", "energy"]
    assert "priorities" not in data["profile"]["from_profile"]
    assert all(item["feasible"] for item in data["ranking"])  # явний мінімум 0 перекрив поріг профілю


@pytest.mark.parametrize("extra", [
    {"mission_profile": "robot"},
    {"mission_profile": "uncrewed", "crew": 2},
    {"mission_profile": "crewed", "crew": 0},
    {"mission_profile": "crewed", "crew": 99},
    {"crew": 2},  # без профілю crew не приймається
])
def test_invalid_profile_requests(client, extra):
    res = rank(client, **extra)
    assert res.status_code == 400, res.get_json()
    assert_valid(api_validator("Error"), res.get_json())
