"""POST /api/launch-ranking: контракт, рейтинг стартів, маса з моделі місії, фільтри, помилки (задача B15)."""

import pytest

from tests.test_contracts import api_validator, assert_valid

pytest.importorskip("naif_de440")

BASE = {"lat": -89.67, "lon": 129.78, "datetime": "2027-07-01T00:00:00Z", "mass_moon_kg": 2000}


def post(client, **kw):
    return client.post("/api/launch-ranking", json={**BASE, **kw})


def test_response_matches_contract(client):
    res = post(client)
    assert res.status_code == 200
    data = res.get_json()
    assert_valid(api_validator("LaunchRankingResponse"), data)
    assert data["provisional"] is True
    assert data["departure_utc"] == "2027-07-01T00:00:00Z"
    assert set(data["transfers"]) == {"direct", "low_energy"}
    assert data["transfers"]["direct"]["method"] == "patched_conic"
    assert data["transfers"]["low_energy"]["method"] == "estimate"
    assert 0 < data["moon_declination_deg"] < 29
    assert data["leader_explanation"]


def test_ranking_order_and_ranges(client):
    data = post(client, limit=200).get_json()
    opts = data["options"]
    assert data["total_options"] == len(opts) > 0
    assert [o["rank"] for o in opts] == list(range(1, len(opts) + 1))
    fits = [o["fits"] for o in opts]
    assert fits == sorted(fits, reverse=True)  # допустимі — першими
    for o in opts:
        assert o["dv_total_m_s"][0] <= o["dv_total_m_s"][1]
        assert o["launch_cost_usd"][0] <= o["launch_cost_usd"][1]
        assert o["risk"]["range"][0] <= o["risk"]["p"] <= o["risk"]["range"][1]
        assert "failure_probability" in o["provisional_fields"]
    assert all(o["fits"] for o in opts if o["pareto"])


def test_equatorial_site_needs_less_fuel(client):
    opts = post(client, trajectories=["direct"], limit=200).get_json()["options"]
    best = {}
    for o in opts:
        best[o["site"]["id"]] = min(best.get(o["site"]["id"], float("inf")), o["mass_leo_kg"])
    assert best["kourou"] < best["cape-canaveral"]
    kourou = next(o for o in opts if o["site"]["id"] == "kourou")
    assert kourou["windows_per_day"] == 2


def test_limit_vehicle_and_design_target_filters(client):
    data = post(client, limit=1).get_json()
    assert len(data["options"]) == 1 and data["total_options"] > 1

    sls = post(client, vehicle="sls-block-1", limit=200).get_json()
    assert {o["vehicle"]["id"] for o in sls["options"]} == {"sls-block-1"}
    assert all(o["capacity_basis"] == "tli" for o in sls["options"])

    no_design = post(client, include_design_targets=False, limit=200).get_json()
    assert "long-march-10" not in {o["vehicle"]["id"] for o in no_design["options"]}
    assert any(e["vehicle_id"] == "long-march-10" for e in no_design["excluded"])


def test_priorities_change_the_leader_factor(client):
    fuel = post(client, priorities=["fuel"], trajectories=["direct", "low_energy"]).get_json()
    speed = post(client, priorities=["speed"], trajectories=["direct", "low_energy"]).get_json()
    assert fuel["options"][0]["trajectory"] == "low_energy"  # економна — легша
    assert speed["options"][0]["trajectory"] == "direct"  # пряма — швидша
    assert set(fuel["options"][0]["factors"]) == {"fuel"}


def test_mass_from_mission_model(client):
    body = {k: v for k, v in BASE.items() if k != "mass_moon_kg"}
    res = client.post("/api/launch-ranking", json={**body, "crew": 2, "days": 10, "limit": 1})
    assert res.status_code == 200
    mission = client.post("/api/mission", json={"crew": 2, "days": 10}).get_json()
    assert res.get_json()["mass_moon_kg"] == pytest.approx(mission["payload"]["total_kg"])


def test_heavy_mission_does_not_fit_small_rockets(client):
    opts = post(client, mass_moon_kg=20000, trajectories=["direct"], limit=200).get_json()["options"]
    vc2 = next(o for o in opts if o["vehicle"]["id"] == "vulcan-vc2")
    assert not vc2["fits"] and vc2["fit_note"]
    multi = post(client, mass_moon_kg=20000, trajectories=["direct"], limit=200,
                 allow_multiple_launches=True).get_json()["options"]
    assert next(o for o in multi if o["vehicle"]["id"] == "vulcan-vc2")["fits"]


@pytest.mark.parametrize(("body", "status"), [
    ({}, 400),
    ({"lat": 95, "lon": 0}, 400),
    ({**BASE, "vehicle": "no-such-rocket"}, 404),
    ({**BASE, "priorities": ["fuel", "fuel"]}, 400),
    ({**BASE, "priorities": ["beauty"]}, 400),
    ({**BASE, "trajectories": []}, 400),
    ({**BASE, "mode": "best"}, 400),
    ({**BASE, "limit": 0}, 400),
    ({**BASE, "datetime": "вчора"}, 400),
    ({**BASE, "mass_moon_kg": -1}, 400),
    ({**BASE, "crew": 1}, 400),  # mass_moon_kg разом із моделлю місії
    ({**BASE, "colour": "red"}, 400),
])
def test_errors(client, body, status):
    res = client.post("/api/launch-ranking", json=body)
    assert res.status_code == status
    assert_valid(api_validator("Error"), res.get_json())
