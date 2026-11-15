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


def test_calendar_is_the_landing_date_and_departure_is_computed_backwards(client):
    data = plan(client, start="2027-03-10T00:00:00Z", end="2027-03-20T00:00:00Z").get_json()
    assert_valid(api_validator("PlanResponse"), data)
    sp = data["surface_period"]
    assert sp["anchor"] == "landing" and sp["after_arrival"] is False
    assert sp["start"] == "2027-03-10T00:00:00Z" and data["period"]["start"] == sp["start"]
    assert 3.0 <= sp["assumed_flight_days"] <= 5.0
    from datetime import datetime, timedelta
    dep = datetime.fromisoformat(data["departure_utc"].replace("Z", "+00:00"))
    land = datetime.fromisoformat(sp["start"].replace("Z", "+00:00"))
    assert abs((land - dep).total_seconds() / 86400.0 - sp["assumed_flight_days"]) < 0.01
    arrival = datetime.fromisoformat(data["plans"][0]["route"]["arrival_utc"][0].replace("Z", "+00:00"))
    assert abs((arrival - land).total_seconds()) <= timedelta(days=2).total_seconds()
    assert any("дата посадки" in n for n in data["notes"])
    assert data["period"]["period_h"] == 240.0  # довжина періоду з start..end збережена


def test_low_energy_goes_back_105_days_from_the_landing_date(client):
    slow = plan(client, trajectories=["low_energy"]).get_json()
    assert slow["surface_period"]["assumed_flight_days"] == 105.0
    assert slow["departure_utc"] < slow["surface_period"]["start"]


def test_legacy_departure_anchor_still_shifts_the_surface_period_after_arrival(client):
    data = plan(client, anchor="departure", departure="2027-01-01T00:00:00Z").get_json()
    sp = data["surface_period"]
    assert sp["anchor"] == "departure" and sp["after_arrival"] is True and sp["assumed_flight_days"] == 4.0
    assert sp["start"] == "2027-01-05T00:00:00Z"
    assert plan(client, anchor="whenever").status_code == 400


def test_surface_period_can_stay_as_requested_and_follows_trajectory(client):
    data = plan(client, anchor="departure", surface_after_arrival=False).get_json()
    assert data["surface_period"]["start"] == "2027-01-01T00:00:00Z" and not data["surface_period"]["after_arrival"]
    slow = plan(client, anchor="departure", trajectories=["low_energy"]).get_json()
    assert slow["surface_period"]["assumed_flight_days"] == 105.0
    assert plan(client, surface_after_arrival="yes").status_code == 400


def test_plan_launch_options_are_passed_through(client):
    data = plan(client, include_design_targets=False, allow_multiple_launches=True).get_json()
    lead = data["plans"][0]["launch"]
    assert lead["vehicle"]["status"] != "design_target"


def test_plan_passes_crew_biometrics_and_reports_supply_shortage(client):
    members = [{"sex": "male", "mass_kg": 90, "height_m": 1.85}, {"sex": "female"}]
    data = plan(client, mission_profile="crewed", days=20, crew_members=members, supply_days=15).get_json()
    assert data["plans"][0]["mission"] is not None or data["notes"]
    lead = data["plans"][0]["mission"]
    if lead:
        assert lead["payload"]["crew"] == 2
        assert [w["kind"] for w in lead["crew_supplies"]["warnings"]] == ["shortage"]


def test_crewed_plan_considers_only_the_direct_trajectory(client):
    data = plan(client, mission_profile="crewed", days=10).get_json()
    assert any("лише пряму траєкторію" in n for n in data["notes"])
    for p in data["plans"]:
        if p["launch"]:
            assert p["launch"]["trajectory"] == "direct"
    assert 3.0 <= data["surface_period"]["assumed_flight_days"] <= 5.0


def test_crewed_plan_rejects_the_low_energy_trajectory(client):
    assert plan(client, mission_profile="crewed", days=10, trajectories=["low_energy"]).status_code == 400
    assert plan(client, mission_profile="crewed", days=10, trajectories=["direct"]).status_code == 200
    assert plan(client, crew_members=[{"sex": "male"}], mission_profile="crewed", days=5,
                trajectories=["direct", "low_energy"]).status_code == 400


def test_plan_can_be_restricted_to_one_launch_site(client):
    sites = client.get("/api/launch-sites").get_json()
    ids = [s["id"] for s in sites]
    chosen = "kourou" if "kourou" in ids else ids[0]
    data = plan(client, launch_site_id=chosen).get_json()
    assert_valid(api_validator("PlanResponse"), data)
    for p in data["plans"]:
        if p["launch"]:
            assert p["launch"]["site"]["id"] == chosen
    assert plan(client, launch_site_id="no-such-site").status_code == 400


def test_plan_uses_the_landing_point_chosen_on_step_5(client):
    data = plan(client, landing_point={"lat": -85.0, "lon": 30.0}, region={"lat_min": -90, "lat_max": -60}).get_json()
    assert_valid(api_validator("PlanResponse"), data)
    assert data["landing_source"] == "selected" and data["landing_evaluated"] == 1
    site = data["plans"][0]["landing"]["moon_site"]
    assert (site["lat"], site["lon"]) == (-85.0, 30.0)
    assert len(data["plans"]) == 1
    assert any("кроку 5" in n for n in data["notes"])
    assert plan(client).get_json()["landing_source"] == "search"


@pytest.mark.parametrize("point", [{"lat": 91, "lon": 0}, {"lat": 0}, {"lat": "x", "lon": 1}, "pole"])
def test_invalid_landing_point_is_rejected(client, point):
    assert plan(client, landing_point=point).status_code == 400


def test_plan_gives_the_exact_launch_time_of_day(client):
    data = plan(client, landing_point={"lat": -85.0, "lon": 30.0}).get_json()
    p = data["plans"][0]
    assert_valid(api_validator("PlanResponse"), data)
    assert "launch_windows_utc" in p
    if p["launch_windows_utc"]:  # пряма траєкторія з космодрому, що досягає площини
        assert p["route"]["departure_utc"] == p["launch_windows_utc"][0]
        assert p["route"]["departure_utc"][:10] == data["departure_utc"][:10]
        assert p["route"]["departure_utc"] != data["departure_utc"]  # не опівночі, а справжній момент
    assert not any("далеке від дати посадки" in n for n in data["notes"])


def test_no_launch_option_explains_why_for_a_rocket_without_site(client):
    """Ракета без майданчика в каталозі (проєктна ціль): варіанта запуску немає — і пояснення називає причину."""
    data = plan(client, vehicle="new-glenn-9x4").get_json()
    assert_valid(api_validator("PlanResponse"), data)
    lead = data["plans"][0]
    assert lead["launch"] is None
    assert "new-glenn-9x4" in lead["launch_explanation"] and "майданчика немає" in lead["launch_explanation"]
    assert lead["launch_explanation"] in data["explanation"]


def test_no_launch_option_when_rocket_and_site_do_not_match(client):
    data = plan(client, vehicle="new-glenn", launch_site_id="sriharikota").get_json()
    lead = data["plans"][0]
    assert lead["launch"] is None and "не стартує з вибраного майданчика" in lead["launch_explanation"]
