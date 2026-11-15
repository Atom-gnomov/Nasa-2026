"""Цілі місії (M25): дані, ядро, ендпоінт."""

import json
from pathlib import Path

import pytest

from app.core import mission_goal
from tests.test_contracts import api_validator, assert_valid

ROOT = Path(__file__).resolve().parents[1]
ROWS = json.loads((ROOT / "app" / "data" / "mission_goals.json").read_text(encoding="utf-8"))["goals"]


def test_catalog_has_the_five_goals_with_sources_and_valid_defaults():
    goals = mission_goal.load_goals(ROWS)
    assert {g.id for g in goals} == {"ice", "samples", "science", "technology", "base"}
    for g in goals:
        assert g.sources and all(s["url"].startswith("https://") for s in g.sources)
        assert g.site_notes and g.name and g.name_en
    by = {g.id: g for g in goals}
    assert by["samples"].mission_profile == "crewed" and by["samples"].stay_days == 7
    assert by["ice"].mission_profile == "uncrewed" and by["ice"].priorities[0] == "comms"


def test_instruments_refer_to_the_equipment_catalog():
    catalog = json.loads((ROOT / "app" / "data" / "equipment_catalog.json").read_text(encoding="utf-8"))
    ids = {i["id"] for i in catalog["items"]}
    for g in mission_goal.load_goals(ROWS):
        assert set(g.instrument_ids) <= ids, g.id


@pytest.mark.parametrize("patch", [
    {"mission_profile": "robot"}, {"stay_days": 0}, {"stay_days": 400}, {"stay_days": True}, {"priorities": []},
    {"priorities": ["energy", "energy"]}, {"priorities": ["luck"]}, {"sources": []}])
def test_invalid_goal_rows_are_rejected(patch):
    with pytest.raises(ValueError):
        mission_goal.parse_goal({**ROWS[0], **patch})


def test_duplicate_ids_are_rejected_and_find_goal_works():
    with pytest.raises(ValueError):
        mission_goal.load_goals([ROWS[0], ROWS[0]])
    goals = mission_goal.load_goals(ROWS)
    assert mission_goal.find_goal(goals, "ice").name == "Пошук води й льоду"
    assert mission_goal.find_goal(goals, "nope") is None


def test_defaults_are_what_the_next_steps_get():
    g = mission_goal.find_goal(mission_goal.load_goals(ROWS), "base")
    expected = {"mission_profile": "crewed", "stay_days": 30, "priorities": ["energy", "comms", "radiation"]}
    assert g.defaults() == expected


def test_endpoint_matches_the_contract(client):
    res = client.get("/api/mission-goals")
    assert res.status_code == 200
    data = res.get_json()
    assert_valid(api_validator("MissionGoals"), data)
    assert data["provisional"] is True and len(data["goals"]) == 5
    assert data["goals"][0]["defaults"]["priorities"]
