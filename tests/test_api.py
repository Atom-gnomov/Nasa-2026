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


def test_metrics_not_implemented_yet(client):
    # Поки ефемериди не підключено — 501. Оновити тест, коли модуль ephemeris буде готовий.
    res = client.get("/api/metrics?lat=-89.5&lon=0&datetime=2027-01-01T00:00")
    assert res.status_code == 501


def test_compare_needs_two_sites(client):
    assert client.get("/api/compare?site=apollo-11").status_code == 400
