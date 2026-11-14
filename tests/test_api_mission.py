"""POST /api/mission: контракт, безпілотна й пілотована місії, широта старту, помилки (задача B9)."""

import pytest

from app.core import cost, payload, risk
from tests.test_contracts import api_validator, assert_valid


def post(client, body):
    return client.post("/api/mission", json=body)


def test_empty_request_is_an_uncrewed_mission_and_matches_contract(client):
    res = post(client, {})
    assert res.status_code == 200
    data = res.get_json()
    assert_valid(api_validator("MissionResponse"), data)
    assert data["provisional"] is True
    assert data["launch_lat"] == 0.0 and data["launch_site_id"] is None
    assert data["payload"]["crew"] == 0
    assert data["payload"]["masses_kg"]["life_support"] == 0 and data["payload"]["masses_kg"]["comfort"] == 0
    assert data["risk"]["p_crew_loss"] is None and data["risk"]["crew_band"] is None


def test_response_equals_the_core_models(client):
    body = {"crew": 3, "days": 20, "sizes": {"equipment": "extended", "life_support": 0.7, "comfort": "min"},
            "trajectory": "low_energy", "launch_lat": 28.5, "longest_night_h": 250}
    data = post(client, body).get_json()
    budget = payload.payload_budget(body["sizes"], crew=3, days=20, longest_night_h=250)
    estimate = cost.mission_cost(budget.masses_kg, trajectory="low_energy", latitude_deg=28.5)
    assessment = risk.assess(estimate.utilization, estimate.mass_moon_kg, budget.sizes, crew=3,
                             trajectory="low_energy")
    assert data["payload"]["total_kg"] == pytest.approx(budget.total_kg)
    assert data["cost"]["total_usd"] == pytest.approx(list(estimate.total_usd))
    assert data["risk"]["p_total"] == pytest.approx(assessment.p_total)
    assert data["risk"]["p_crew_loss"] == pytest.approx(assessment.p_crew_loss)
    assert data["risk"]["band_label"] == assessment.band_label


def test_launch_site_id_sets_latitude_from_catalog(client):
    kourou = post(client, {"launch_site_id": "kourou"}).get_json()
    equator = post(client, {}).get_json()
    assert kourou["launch_site_id"] == "kourou" and 5 < kourou["launch_lat"] < 6
    high = post(client, {"launch_lat": 60}).get_json()
    assert equator["cost"]["site_factor"] <= kourou["cost"]["site_factor"] < high["cost"]["site_factor"]


def test_crewed_mission_is_heavier_and_has_crew_risk(client):
    uncrewed = post(client, {"days": 14}).get_json()
    crewed = post(client, {"crew": 4, "days": 14}).get_json()
    assert crewed["payload"]["total_kg"] > uncrewed["payload"]["total_kg"]
    assert crewed["cost"]["total_usd"][0] > uncrewed["cost"]["total_usd"][0]
    assert crewed["risk"]["p_crew_loss"] is not None and crewed["risk"]["crew_band_label"]


def test_low_energy_needs_less_mass_in_leo_and_takes_longer(client):
    direct = post(client, {"crew": 2, "days": 10}).get_json()["cost"]
    slow = post(client, {"crew": 2, "days": 10, "trajectory": "low_energy"}).get_json()["cost"]
    assert slow["mass_leo_kg"] < direct["mass_leo_kg"]
    assert slow["flight_time_days"][0] > direct["flight_time_days"][1]


@pytest.mark.parametrize("body, status", [
    ({"crew": 7}, 400), ({"crew": -1}, 400), ({"crew": 1.5}, 400), ({"crew": True}, 400),
    ({"days": -1}, 400), ({"days": 1000}, 400), ({"days": "10"}, 400),
    ({"longest_night_h": -5}, 400),
    ({"sizes": {"equipment": "huge"}}, 400), ({"sizes": {"comfort": 1.5}}, 400),
    ({"sizes": {"weapons": "max"}}, 400), ({"sizes": "max"}, 400),
    ({"trajectory": "teleport"}, 400),
    ({"launch_lat": 91}, 400), ({"launch_lat": "x"}, 400),
    ({"launch_site_id": "kourou", "launch_lat": 5}, 400), ({"launch_site_id": 5}, 400),
    ({"launch_site_id": "no-such-site"}, 404),
    ({"surprise": 1}, 400),
])
def test_invalid_requests(client, body, status):
    res = post(client, body)
    assert res.status_code == status, res.get_json()
    assert_valid(api_validator("Error"), res.get_json())


def test_non_object_body_is_rejected(client):
    res = client.post("/api/mission", json=[1, 2, 3])
    assert res.status_code == 400
    assert_valid(api_validator("Error"), res.get_json())


def test_no_body_is_treated_as_defaults(client):
    assert client.post("/api/mission").status_code == 200
