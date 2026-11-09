import pytest


def test_health(client):
    assert client.get("/api/health").get_json() == {"status": "ok"}


def test_sites_list(client):
    sites = client.get("/api/sites").get_json()
    assert any(s["id"] == "apollo-11" for s in sites)
    for s in sites:
        assert -90 <= s["lat"] <= 90


def test_site_not_found(client):
    res = client.get("/api/sites/nope")
    assert res.status_code == 404
    assert res.get_json()["error"]


def test_dsn_stations(client):
    ids = {s["id"] for s in client.get("/api/dsn").get_json()}
    assert ids == {"goldstone", "madrid", "canberra"}


def test_metrics_validation(client):
    assert client.get("/api/metrics?lat=100&lon=0").status_code == 400
    assert client.get("/api/metrics?lon=0").status_code == 400
    assert client.get("/api/metrics?lat=0&lon=0&datetime=bad").status_code == 400


def test_metrics_south_pole(client):
    pytest.importorskip("naif_de440")
    res = client.get("/api/metrics?lat=-89.5&lon=0&datetime=2027-01-01T00:00&height=2")
    assert res.status_code == 200
    m = res.get_json()
    assert -2.5 < m["sun_elevation_deg"] < 2.5
    assert -8 < m["earth_elevation_deg"] < 8
    assert 1.18 < m["signal_delay_s"] < 1.37
    # Полярне «літо»: Сонце не заходить увесь пошуковий інтервал (30 діб) — подій немає.
    assert m["sun_visible_fraction"] == 1.0
    assert m["hours_to_sunset"] is None and m["hours_to_sunrise"] is None
    assert m["event_search_hours"] == 720


def test_metrics_south_pole_events(client):
    pytest.importorskip("naif_de440")
    m = client.get("/api/metrics?lat=-89.5&lon=0&datetime=2027-07-01T00:00&height=2").get_json()
    assert m["earth_visible"] is True
    assert 0 < m["hours_to_earthset"] < m["hours_to_earthrise"]
    assert 0 < m["hours_to_sunrise"] < m["hours_to_sunset"]
    assert m["recommended_station"] == "canberra"


def test_metrics_apollo_11_earth_up(client):
    pytest.importorskip("naif_de440")
    m = client.get("/api/metrics?lat=0.674&lon=23.473&datetime=2027-03-01T12:00").get_json()
    assert m["earth_visible"] is True
    assert m["earth_elevation_deg"] > 55
    assert m["hours_to_earthset"] is None  # Земля на ближньому боці не заходить
    assert m["recommended_station"] in {"goldstone", "madrid", "canberra", None}


def test_metrics_height_validation(client):
    assert client.get("/api/metrics?lat=0&lon=0&height=-5").status_code == 400


def test_compare_two_sites(client):
    pytest.importorskip("naif_de440")
    res = client.get("/api/compare?site=apollo-11&site=south-pole&datetime=2027-01-01T00:00")
    assert res.status_code == 200
    assert [r["site"]["id"] for r in res.get_json()] == ["apollo-11", "south-pole"]


def test_compare_needs_two_sites(client):
    assert client.get("/api/compare?site=apollo-11").status_code == 400
