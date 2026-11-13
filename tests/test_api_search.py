"""Тести POST /api/search: контракт, пошук у регіоні, вимоги, бюджет часу, помилки."""

import pytest

from tests.test_contracts import api_validator, assert_valid

pytest.importorskip("naif_de440")

BASE = {"start": "2027-01-01T00:00:00Z", "end": "2027-01-11T00:00:00Z",
        "region": {"lat_min": -90, "lat_max": -85}, "grid_step_deg": 2.5}


def search(client, **extra):
    return client.post("/api/search", json={**BASE, **extra})


def test_search_response_matches_contract(client):
    res = search(client, priorities=["energy", "comms", "radiation"], limit=5)
    assert res.status_code == 200
    data = res.get_json()
    assert_valid(api_validator("SearchResponse"), data)
    assert 1 <= len(data["chains"]) <= 5
    assert [c["rank"] for c in data["chains"]] == list(range(1, len(data["chains"]) + 1))
    scores = [c["score_pct"] for c in data["chains"] if c["feasible"]]
    assert scores == sorted(scores, reverse=True)
    assert data["grid"]["evaluated"] == data["grid"]["candidates"] and not data["grid"]["truncated"]
    assert all(c["launch_site_id"] is None for c in data["chains"])
    assert data["comparison"]["a_rank"] == 1 and data["comparison"]["b_rank"] == 2


def test_candidates_stay_in_region_and_have_a_station(client):
    data = search(client, limit=100).get_json()
    for c in data["chains"]:
        assert -90 <= c["moon_site"]["lat"] <= -85
        if c["dsn_station_id"]:
            assert c["dsn_hours"] > 0 and c["dsn_station_id"] in {"goldstone", "madrid", "canberra"}


def test_default_region_is_south_polar_cap(client):
    data = client.post("/api/search", json={"start": "2027-01-01T00:00:00Z", "end": "2027-01-05T00:00:00Z",
                                            "grid_step_deg": 5, "limit": 100}).get_json()
    assert all(-90 <= c["moon_site"]["lat"] <= -80 for c in data["chains"])


def test_include_catalog_adds_named_sites_without_duplicates(client):
    data = search(client, include_catalog=True, limit=100).get_json()
    named = {c["moon_site"]["site_id"] for c in data["chains"] if c["moon_site"]["site_id"]}
    assert {"south-pole", "shackleton"} <= named
    coords = [(c["moon_site"]["lat"], c["moon_site"]["lon"]) for c in data["chains"]]
    assert len({(round(a, 4), round(b, 4)) for a, b in coords}) == len(coords)


def test_catalog_sites_outside_the_region_are_not_added(client):
    data = search(client, include_catalog=True, limit=100).get_json()  # область 85–90° пд. ш.
    named = {c["moon_site"]["site_id"] for c in data["chains"] if c["moon_site"]["site_id"]}
    assert not named & {"apollo-11", "apollo-17", "chandrayaan-3"}
    assert all(-90 <= c["moon_site"]["lat"] <= -85 for c in data["chains"])
    wide = search(client, include_catalog=True, region={"lat_min": -90, "lat_max": 30}, grid_step_deg=30,
                  limit=100).get_json()
    assert "apollo-11" in {c["moon_site"]["site_id"] for c in wide["chains"]}


def test_requirements_push_infeasible_down_with_violations(client):
    data = search(client, min_sun_hours=10_000, limit=100).get_json()  # період лише 240 год
    assert not any(c["feasible"] for c in data["chains"])
    assert all(c["violations"][0]["requirement"] == "min_sun_hours" for c in data["chains"])
    mixed = search(client, min_comm_hours=100, limit=100).get_json()["chains"]
    flags = [c["feasible"] for c in mixed]
    assert flags == sorted(flags, reverse=True)  # допустимі йдуть першими


def test_priority_order_changes_the_winner(client):
    pts = {"region": {"lat_min": -90, "lat_max": 0}, "grid_step_deg": 30, "include_catalog": False, "limit": 1}
    energy = search(client, **pts, priorities=["energy", "comms"]).get_json()["chains"][0]["moon_site"]
    comms = search(client, **pts, priorities=["comms", "energy"]).get_json()["chains"][0]["moon_site"]
    assert energy != comms


def test_maximin_mode(client):
    data = search(client, mode="maximin", limit=100).get_json()
    for c in data["chains"]:
        assert c["score_pct"] == pytest.approx(100 * min(c["factors"].values()), abs=0.01)


def test_time_budget_truncates_but_returns_results(client, monkeypatch):
    from app.services import search as svc

    monkeypatch.setattr(svc, "BUDGET_S", 1e6)
    assert client.post("/api/search", json=BASE).get_json()["grid"]["truncated"] is False
    monkeypatch.setattr(svc, "BUDGET_S", 1.0)
    ticks = iter(range(0, 10_000, 100))  # кожен виклик «годинника» додає 100 с — бюджет вичерпується одразу
    monkeypatch.setattr(svc, "_now", lambda: float(next(ticks)))
    data = client.post("/api/search", json=BASE).get_json()
    assert_valid(api_validator("SearchResponse"), data)
    assert data["grid"]["truncated"] is True
    assert data["grid"]["evaluated"] == svc.MIN_EVALUATED < data["grid"]["candidates"]
    assert len(data["chains"]) == svc.MIN_EVALUATED


@pytest.mark.parametrize("extra", [
    {"launch_site_ids": ["kourou"]},
    {"trajectory": "direct"},
    {"priorities": ["cost"]},
    {"mode": "average"},
    {"params": {"bogus": 1}},
    {"limit": 0},
    {"limit": 1000},
    {"step_h": 0},
    {"grid_step_deg": 0.01},
    {"min_sun_hours": -5},
    {"min_sun_hours": "багато"},
    {"region": {"lat_min": -80, "lat_max": -90}},
    {"region": {"lat_min": -90, "lat_max": -80, "bogus": 1}},
    {"grid_step_deg": 0.25, "region": {"lat_min": -90, "lat_max": 90}},  # занадто багато кандидатів
    {"end": "2027-01-01T00:00:00Z"},  # кінець не пізніше за початок
    {"start": "не дата"},
])
def test_search_errors_follow_contract(client, extra):
    res = search(client, **extra)
    assert res.status_code == 400
    assert_valid(api_validator("Error"), res.get_json())


def test_search_rejects_non_json(client):
    assert client.post("/api/search", data="x", content_type="text/plain").status_code == 400


def test_temperature_factor_unavailable_without_diviner_data(client):
    res = search(client, priorities=["energy", "temperature"])
    assert res.status_code in (400, 503)
    assert_valid(api_validator("Error"), res.get_json())
