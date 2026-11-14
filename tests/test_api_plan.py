"""Тести POST /api/plan (B18): оркестрація /search → /launch-ranking → /mission, автовибір за вимогами."""

import pytest

from app.services import ranking
from tests.test_contracts import api_validator, assert_valid

pytest.importorskip("naif_de440")

BASE = {"start": "2027-01-01T00:00:00Z", "end": "2027-01-11T00:00:00Z",
        "region": {"lat_min": -90, "lat_max": -85}, "grid_step_deg": 2.5,
        "days": 5, "landing_candidates": 2, "limit": 3}


def plan(client, **extra):
    return client.post("/api/plan", json={**BASE, **extra})


def test_plan_returns_ranked_end_to_end_plans(client):
    res = plan(client)
    assert res.status_code == 200, res.get_json()
    data = res.get_json()
    assert_valid(api_validator("PlanResponse"), data)
    assert data["provisional"] is True and data["hard_requirements_met"] is True
    assert 1 <= len(data["plans"]) <= 2
    assert [p["rank"] for p in data["plans"]] == list(range(1, len(data["plans"]) + 1))
    lead = data["plans"][0]
    assert lead["launch"]["site"]["id"] and lead["launch"]["vehicle"]["id"]
    assert lead["route"]["moon_site"]["lat"] == lead["landing"]["moon_site"]["lat"]
    assert lead["route"]["launch_site"]["id"] == lead["launch"]["site"]["id"]
    assert lead["route"]["arrival_utc"] and lead["route"]["departure_utc"]
    assert lead["mass_moon_kg"] > 0
    assert data["explanation"].startswith("Обрано")
    assert data["plans"][1:] == [] or data["plans"][1]["mission"] is None  # повна місія — лише для лідера


def test_plan_leader_has_full_mission_or_note(client):
    data = plan(client).get_json()
    lead = data["plans"][0]
    assert lead["mission"] is not None or data["notes"]
    if lead["mission"]:
        assert lead["mission"]["launch_site_id"] == lead["launch"]["site"]["id"]


@pytest.fixture
def steep_everywhere(monkeypatch):
    monkeypatch.setattr(ranking, "slope_deg", lambda lat, lon: 15.0)


def test_plan_without_feasible_site_picks_fewest_violations_and_says_so(client, steep_everywhere):
    data = plan(client, max_slope_deg=10).get_json()
    assert data["hard_requirements_met"] is False
    lead = data["plans"][0]
    assert lead["requirements"]["feasible"] is False
    assert lead["requirements"]["violations"][0]["requirement"] == "max_slope_deg"
    assert data["explanation"].startswith("Жодне місце не виконує")


def test_plan_marks_unchecked_requirements_without_dem(client):
    data = plan(client, max_slope_deg=10).get_json()
    assert data["hard_requirements_met"] is True
    assert data["plans"][0]["requirements"]["unchecked"] == ["max_slope_deg"]
    assert "не перевірено" in data["explanation"]


def test_plan_vehicle_filter_and_unknown_vehicle(client):
    assert plan(client, vehicle="no-such-rocket").status_code == 404


@pytest.mark.parametrize("extra", [{"landing_candidates": 0}, {"limit": 100}, {"bogus": 1}, {"departure": "завтра"},
                                   {"mission_profile": "uncrewed", "crew": 2}, {"max_slope_deg": 200}])
def test_plan_rejects_bad_input(client, extra):
    res = plan(client, **extra)
    assert res.status_code == 400, res.get_json()
    assert "error" in res.get_json() or "message" in res.get_json()


def test_plan_searches_the_best_departure_date(client):
    data = plan(client, departure_days=3, departure="2027-01-01T00:00:00Z").get_json()
    assert_valid(api_validator("PlanResponse"), data)
    lead = data["plans"][0]
    window = lead["departure_window"]
    assert [d["date"] for d in window["days"]] == ["2027-01-01", "2027-01-02", "2027-01-03"]
    assert window["best"]["score_pct"] == max(d["score_pct"] for d in window["days"])
    assert lead["route"]["departure_utc"].startswith(window["best"]["date"])


def test_plan_without_departure_days_has_no_window(client):
    assert plan(client).get_json()["plans"][0]["departure_window"] is None


def test_plan_departure_days_out_of_range(client):
    assert plan(client, departure_days=0).status_code == 400
    assert plan(client, departure_days=61).status_code == 400


def test_surface_period_follows_arrival_by_default(client):
    data = plan(client, departure="2027-01-01T00:00:00Z").get_json()
    assert_valid(api_validator("PlanResponse"), data)
    sp = data["surface_period"]
    assert sp["after_arrival"] is True and sp["assumed_flight_days"] == 4.0
    assert sp["start"] == "2027-01-05T00:00:00Z"
    assert data["period"]["start"] == sp["start"]  # /search оцінював саме цей період
    assert (data["period"]["period_h"]) == 240.0  # довжина періоду з start..end збережена


def test_surface_period_can_stay_as_requested_and_follows_trajectory(client):
    data = plan(client, surface_after_arrival=False).get_json()
    assert data["surface_period"]["start"] == "2027-01-01T00:00:00Z" and not data["surface_period"]["after_arrival"]
    slow = plan(client, trajectories=["low_energy"]).get_json()
    assert slow["surface_period"]["assumed_flight_days"] == 105.0
    assert plan(client, surface_after_arrival="yes").status_code == 400


def test_plan_launch_options_are_passed_through(client):
    data = plan(client, include_design_targets=False, allow_multiple_launches=True).get_json()
    lead = data["plans"][0]["launch"]
    assert lead["vehicle"]["status"] != "design_target"
