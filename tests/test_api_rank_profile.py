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


def test_crewed_profile_sets_priorities_and_reports_what_it_set(client):
    res = rank(client, mission_profile="crewed", crew=3)
    assert res.status_code == 200
    data = res.get_json()
    assert_valid(api_validator("RankResponse"), data)
    assert data["priorities"][0] == "radiation"
    profile = data["profile"]
    assert profile["crew"] == 3 and "priorities" in profile["from_profile"]
    assert profile["limits"]["landing_slope_deg"]["id"] == "landing-slope-100m"


def test_explicit_priorities_and_requirements_win_over_the_profile(client):
    res = rank(client, mission_profile="crewed", crew=2, priorities=["comms", "energy"],
               requirements={"max_slope_deg": 90})
    data = res.get_json()
    assert data["priorities"] == ["comms", "energy"]
    assert "priorities" not in data["profile"]["from_profile"]
    assert all(item["feasible"] for item in data["ranking"])  # явний допустимий нахил 90° перекрив поріг профілю


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


# ---------- M23: вимоги до місця посадки: нахил (жорстка), видимість Землі й Сонця (м'які) ----------
@pytest.fixture
def slopes(monkeypatch):
    """Нахил підміняємо (DEM у тестах немає): Apollo 11 — положистий, полюс — крутий."""
    from app.services import ranking

    table = {"apollo-11": 3.0, "pole": 15.0}

    def fake(lat, lon):
        return table["pole"] if lat < -80 else table["apollo-11"]

    monkeypatch.setattr(ranking, "slope_deg", fake)


def _by_name(data):
    """Ключ — site_id для місць каталогу, інакше назва точки."""
    return {(item["point"]["site_id"] or item["point"]["name"]): item for item in data["ranking"]}


def test_explicit_hard_slope_requirement_filters_steep_points(client, slopes):
    data = rank(client, requirements={"max_slope_deg": 10}).get_json()
    assert_valid(api_validator("RankResponse"), data)
    items = _by_name(data)
    flat, steep = items["apollo-11"], items["Південний полюс"]
    assert flat["feasible"] and flat["summary"]["slope_deg"] == 3.0
    assert not steep["feasible"]
    assert steep["violations"] == [{"requirement": "max_slope_deg", "value": 15.0, "required": 10.0}]
    assert data["ranking"][0]["point"]["site_id"] == "apollo-11"  # допустима перед недопустимою


def test_crewed_profile_applies_slope_hard_and_visibility_soft(client, slopes):
    data = rank(client, mission_profile="crewed", crew=2).get_json()
    assert_valid(api_validator("RankResponse"), data)
    steep = _by_name(data)["Південний полюс"]
    assert not steep["feasible"] and steep["violations"][0]["requirement"] == "max_slope_deg"  # посадка < 10°
    for item in data["ranking"]:  # м'які вимоги не роблять точку недопустимою: лише попередження
        assert all(w["requirement"] in ("min_earth_fraction", "min_sun_fraction") for w in item["warnings"])
        assert item["feasible"] == (not item["violations"])


def test_uncrewed_profile_has_no_landing_requirements_by_default(client, slopes):
    data = rank(client, mission_profile="uncrewed").get_json()
    assert all(item["feasible"] and not item["violations"] and not item["warnings"] for item in data["ranking"])
    assert all("slope_deg" not in item["summary"] for item in data["ranking"])  # нахил не потрібен — не запитуємо


def test_explicit_slope_overrides_the_profile_threshold(client, slopes):
    strict = rank(client, mission_profile="crewed", crew=2, requirements={"max_slope_deg": 2}).get_json()
    assert not _by_name(strict)["apollo-11"]["feasible"]  # 3° > 2°: явне значення суворіше за 10° профілю
    lax = rank(client, mission_profile="crewed", crew=2, requirements={"max_slope_deg": 30}).get_json()
    assert _by_name(lax)["Південний полюс"]["feasible"]  # явне 30° перекрило 10° профілю


def test_unknown_slope_without_dem_is_unchecked_not_violated(client):
    """Без DEM (як у CI) нахил невідомий: вимога не перевірена, точки не відкидаються, і це видно."""
    data = rank(client, requirements={"max_slope_deg": 10}).get_json()
    assert_valid(api_validator("RankResponse"), data)
    for item in data["ranking"]:
        assert item["feasible"] and not item["violations"]
        assert item["unchecked"] == ["max_slope_deg"] and "slope_deg" not in item["summary"]


def test_soft_visibility_requirement_lowers_score_and_reports_a_warning(client):
    plain = _by_name(rank(client).get_json())
    soft = _by_name(rank(client, requirements={"min_earth_fraction": 1.0}).get_json())
    for name, item in soft.items():
        assert item["feasible"]
        if item["warnings"]:
            assert item["score_pct"] < plain[name]["score_pct"]
    assert any(item["warnings"] for item in soft.values())  # на полюсі Земля видна не весь період


@pytest.mark.parametrize("requirements", [{"max_slope_deg": -1}, {"max_slope_deg": 120}, {"min_earth_fraction": 2},
                                          {"min_sun_fraction": -0.1}, {"max_slope_deg": "10"}, {"nonsense": 1}])
def test_invalid_requirements_are_rejected(client, requirements):
    res = rank(client, requirements=requirements)
    assert res.status_code == 400, res.get_json()
    assert_valid(api_validator("Error"), res.get_json())
