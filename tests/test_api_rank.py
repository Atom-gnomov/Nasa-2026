"""Тести /api/rank, /api/events, /api/meta (контракти + поведінка)."""

import pytest

from tests.test_contracts import api_validator, assert_valid

pytest.importorskip("naif_de440")

PERIOD = {"start": "2027-01-01T00:00:00Z", "end": "2027-02-01T00:00:00Z"}


def rank(client, points, **extra):
    return client.post("/api/rank", json={"points": points, **PERIOD, **extra})


def test_meta_matches_contract(client):
    res = client.get("/api/meta")
    assert res.status_code == 200
    meta = res.get_json()
    assert_valid(api_validator("Meta"), meta)
    assert any(s["id"] == "de440" for s in meta["data_sources"])
    assert meta["limits"]["max_rank_points"] == 30


def test_events_equator_and_pole(client):
    q = "start=2027-07-01T00:00&end=2027-07-31T00:00"
    apollo = client.get(f"/api/events?lat=0.674&lon=23.473&{q}")
    assert apollo.status_code == 200
    data = apollo.get_json()
    assert_valid(api_validator("EventList"), data)
    bodies = {e["body"] for e in data["events"]}
    assert "earth" not in bodies  # на ближньому боці Земля не заходить
    sun = [e["kind"] for e in data["events"] if e["body"] == "sun"]
    assert sun.count("rise") >= 1 and sun.count("set") >= 1
    times = [e["datetime"] for e in data["events"]]
    assert times == sorted(times)

    pole = client.get(f"/api/events?lat=-89.5&lon=0&{q}").get_json()
    assert {e["body"] for e in pole["events"]} >= {"earth", "sun", "station:canberra"}


def test_events_validation(client):
    base = "lat=0&lon=0"
    assert client.get(f"/api/events?{base}").status_code == 400
    assert client.get(f"/api/events?{base}&start=2027-02-01&end=2027-01-01").status_code == 400
    assert client.get(f"/api/events?{base}&start=2027-01-01&end=2027-12-01").status_code == 400
    assert client.get("/api/events?lat=99&lon=0&start=2027-01-01&end=2027-01-02").status_code == 400


def test_rank_response_matches_contract(client):
    res = rank(client, [{"site_id": "south-pole"}, {"site_id": "apollo-11"}, {"lat": -85, "lon": 180, "name": "85S"}],
               priorities=["energy", "comms", "radiation"])
    assert res.status_code == 200
    data = res.get_json()
    assert_valid(api_validator("RankResponse"), data)
    assert [r["rank"] for r in data["ranking"]] == [1, 2, 3]
    scores = [r["score_pct"] for r in data["ranking"] if r["feasible"]]
    assert scores == sorted(scores, reverse=True)
    assert sum(data["weights"].values()) == pytest.approx(1.0, abs=1e-3)
    assert data["comparison"]["a_rank"] == 1 and data["comparison"]["b_rank"] == 2


def test_priority_order_changes_the_winner(client):
    pts = [{"site_id": "south-pole"}, {"site_id": "apollo-11"}]  # полюс — світло, Apollo 11 — зв'язок
    first_energy = rank(client, pts, priorities=["energy", "comms"]).get_json()
    first_comms = rank(client, pts, priorities=["comms", "energy"]).get_json()
    assert first_energy["ranking"][0]["point"]["site_id"] == "south-pole"
    assert first_comms["ranking"][0]["point"]["site_id"] == "apollo-11"
    assert first_energy["comparison"]["dominance"] == "tradeoff"


def test_score_does_not_depend_on_other_points(client):
    pair = rank(client, [{"site_id": "south-pole"}, {"site_id": "apollo-11"}]).get_json()
    trio = rank(client, [{"site_id": "south-pole"}, {"site_id": "apollo-11"}, {"lat": 30, "lon": 90}]).get_json()
    pick = lambda d: {r["point"]["site_id"]: r["score_pct"] for r in d["ranking"] if r["point"]["site_id"]}  # noqa: E731
    assert pick(pair) == pick(trio)


def test_requirements_mark_infeasible_and_put_last(client):
    res = rank(client, [{"site_id": "south-pole"}, {"site_id": "apollo-11"}], requirements={"min_sun_hours": 600})
    data = res.get_json()
    assert [r["feasible"] for r in data["ranking"]] == [True, False]
    assert data["ranking"][1]["point"]["site_id"] == "apollo-11"
    assert data["ranking"][1]["violations"][0]["requirement"] == "min_sun_hours"


def test_maximin_mode(client):
    data = rank(client, [{"site_id": "south-pole"}, {"site_id": "apollo-11"}], mode="maximin").get_json()
    for r in data["ranking"]:
        assert r["score_pct"] == pytest.approx(100 * min(r["factors"].values()), abs=0.01)


@pytest.mark.parametrize("body, code", [
    ({"points": [{"site_id": "south-pole"}], **PERIOD}, 400),  # одна точка
    ({"points": [{"site_id": "nope"}, {"site_id": "apollo-11"}], **PERIOD}, 404),
    ({"points": [{"site_id": "apollo-11"}, {"lat": 120, "lon": 0}], **PERIOD}, 400),
    ({"points": [{"site_id": "apollo-11"}, {"name": "без координат"}], **PERIOD}, 400),
    ({"points": [{"site_id": "apollo-11"}, {"site_id": "south-pole"}], **PERIOD, "priorities": ["cost"]}, 400),
    ({"points": [{"site_id": "apollo-11"}, {"site_id": "south-pole"}], **PERIOD, "mode": "average"}, 400),
    ({"points": [{"site_id": "apollo-11"}, {"site_id": "south-pole"}], **PERIOD, "params": {"bogus": 1}}, 400),
    ({"points": [{"site_id": "apollo-11"}, {"site_id": "south-pole"}], "start": "2027-02-01T00:00:00Z",
      "end": "2027-01-01T00:00:00Z"}, 400),
    ({"points": [{"site_id": "apollo-11"}, {"site_id": "south-pole"}], "start": "не дата", "end": "2027-01-01"}, 400),
    ({"start": "2027-01-01", "end": "2027-02-01"}, 400),
])
def test_rank_errors_follow_contract(client, body, code):
    res = client.post("/api/rank", json=body)
    assert res.status_code == code
    assert_valid(api_validator("Error"), res.get_json())


def test_rank_rejects_non_json(client):
    assert client.post("/api/rank", data="x", content_type="text/plain").status_code == 400


def test_temperature_factor_unavailable_without_diviner_data(client):
    res = rank(client, [{"site_id": "apollo-11"}, {"site_id": "south-pole"}], priorities=["energy", "temperature"])
    assert res.status_code == 503
    assert_valid(api_validator("Error"), res.get_json())


def _fake_curve(values):
    return {"diurnal": [{"ltim_h": i, "tbol_k": v} for i, v in enumerate(values)]}


def test_thermal_factor_uses_diurnal_curve(client, monkeypatch):
    from datetime import datetime, timezone

    from app.core.site_score import ScoreParams
    from app.services import ranking, temperature

    curves = {  # знайомі точки: перша завжди в діапазоні, друга — наполовину
        0.674: _fake_curve([250.0, 300.0, 320.0, 280.0]),
        -89.67: _fake_curve([40.0, 300.0, 100.0, 330.0, None]),
    }
    monkeypatch.setattr(temperature, "temperature_point",
                        lambda lat, lon, when: curves[round(lat, 3)] if round(lat, 3) in curves else curves[-89.67])
    now = datetime(2027, 1, 1, tzinfo=timezone.utc)
    assert ranking.thermal_fraction(0.674, 0, now, ScoreParams()) == 1.0
    assert ranking.thermal_fraction(-89.67, 0, now, ScoreParams()) == pytest.approx(0.5)  # None не рахується

    res = rank(client, [{"site_id": "apollo-11"}, {"site_id": "shackleton"}], priorities=["temperature"])
    assert res.status_code == 200
    data = res.get_json()
    assert data["ranking"][0]["point"]["site_id"] == "apollo-11"
    assert data["ranking"][0]["factors"]["temperature"] == 1.0
    assert data["ranking"][1]["summary"]["thermal_fraction"] == pytest.approx(0.5)
    assert_valid(api_validator("RankResponse"), data)
