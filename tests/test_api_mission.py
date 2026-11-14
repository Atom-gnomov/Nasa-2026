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


# ---------- B16: система запуску ----------
def test_launch_systems_list_matches_contract(client):
    res = client.get("/api/launch-systems")
    assert res.status_code == 200
    data = res.get_json()
    assert isinstance(data, list) and len(data) >= 3
    for item in data:
        assert_valid(api_validator("LaunchSystem"), item)
    kinds = {item["kind"] for item in data}
    assert kinds == {"spaceport", "sea_platform", "air_launch"}
    zenit = next(i for i in data if i["id"] == "zenit-3sl-sea-launch")
    assert zenit["capacity_leo_kg"] is None  # у джерелах лише ГПО


def test_mission_with_launch_system_uses_catalog_capacity_and_reports_provisional_fields(client):
    data = post(client, {"crew": 2, "days": 10, "launch_system_id": "ariane-64"}).get_json()
    assert_valid(api_validator("MissionResponse"), data)
    ls = data["launch_system"]
    assert ls["rocket"]["capacity_leo_kg"] == 21600.0
    # D8: база відмови — зі статистики польотів у каталозі; ціни Ariane 64 в каталозі немає
    assert ls["provisional_fields"] == ["price_usd_per_kg"]
    assert ls["fit"]["utilization"] == pytest.approx(data["cost"]["mass_leo_kg"] / 21600.0)
    assert data["launch_site_id"] == "kourou" and 5 < data["launch_lat"] < 6  # широта з місця системи


def test_smaller_system_gives_higher_utilization_than_default_rocket(client):
    base = post(client, {"crew": 2, "days": 10}).get_json()
    small = post(client, {"crew": 2, "days": 10, "launch_system_id": "ariane-62"}).get_json()
    assert small["cost"]["utilization"] > base["cost"]["utilization"]
    assert small["launch_system"]["fit"]["launches"] >= 2


def test_without_launch_system_nothing_changes(client):
    assert post(client, {}).get_json()["launch_system"] is None


def test_air_launch_system_cannot_carry_a_lunar_lander(client):
    data = post(client, {"launch_system_id": "pegasus-xl"}).get_json()
    fit = data["launch_system"]["fit"]
    assert not fit["fits_single_launch"] and "літака-носія" in fit["note"]
    assert data["launch_site_id"] is None and data["launch_lat"] == 0.0  # повітряний старт місця не має


def test_explicit_site_overrides_system_site(client):
    data = post(client, {"launch_system_id": "ariane-64", "launch_lat": 45}).get_json()
    assert data["launch_lat"] == 45 and data["launch_site_id"] is None


@pytest.mark.parametrize("body, status", [
    ({"launch_system_id": "no-such"}, 404),
    ({"launch_system_id": 7}, 400),
    ({"launch_system_id": "zenit-3sl-sea-launch"}, 400),  # немає місткості на НОО
])
def test_invalid_launch_system(client, body, status):
    res = post(client, body)
    assert res.status_code == status, res.get_json()
    assert_valid(api_validator("Error"), res.get_json())


# ---------- B17: профіль місії ----------
def test_without_profile_response_has_no_profile(client):
    assert post(client, {}).get_json()["profile"] is None


def test_uncrewed_profile_forces_zero_crew_and_matches_contract(client):
    data = post(client, {"mission_profile": "uncrewed"}).get_json()
    assert_valid(api_validator("MissionResponse"), data)
    assert data["profile"]["profile"] == "uncrewed" and data["payload"]["crew"] == 0
    assert data["risk"]["p_crew_loss"] is None


def test_crewed_profile_defaults_crew_and_marks_it_as_profile_choice(client):
    data = post(client, {"mission_profile": "crewed", "days": 10}).get_json()
    assert_valid(api_validator("MissionResponse"), data)
    assert data["payload"]["crew"] == data["profile"]["crew"] >= 1
    assert "crew" in data["profile"]["from_profile"]
    assert data["risk"]["p_crew_loss"] is not None


def test_explicit_crew_wins_over_profile_default(client):
    data = post(client, {"mission_profile": "crewed", "crew": 4, "days": 10}).get_json()
    assert data["payload"]["crew"] == 4 and "crew" not in data["profile"]["from_profile"]
    same = post(client, {"crew": 4, "days": 10}).get_json()
    assert data["cost"]["total_usd"] == same["cost"]["total_usd"]  # профіль не змінює розрахунок, лише перевіряє вхід


@pytest.mark.parametrize("body", [
    {"mission_profile": "robot"},
    {"mission_profile": "uncrewed", "crew": 2},
    {"mission_profile": "crewed", "crew": 0},
    {"mission_profile": "crewed", "crew": 7},
    {"mission_profile": "crewed", "crew": True},
])
def test_invalid_profile_requests(client, body):
    res = post(client, body)
    assert res.status_code == 400, res.get_json()
    assert_valid(api_validator("Error"), res.get_json())
