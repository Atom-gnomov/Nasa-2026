def test_index_redirects_to_moon(client):
    res = client.get("/")
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/moon")


def test_moon_page(client):
    res = client.get("/moon")
    assert res.status_code == 200
    assert "calendar-input" in res.get_data(as_text=True)
    assert "metrics-overlay" in res.get_data(as_text=True)


def test_moon_page_has_globe_controls(client):
    html = client.get("/moon").get_data(as_text=True)
    markers = ('data-view="globe"', 'data-view="map"', 'data-view="polar"', "grid-toggle", "relief", "globe_view.js")
    for marker in markers:
        assert marker in html


def test_globe_assets_served_from_cache_dir(app, tmp_path):
    (tmp_path / "globe").mkdir()
    (tmp_path / "globe" / "globe.json").write_text('{"version": 1}', encoding="utf-8")
    app.config["CACHE_DIR"] = tmp_path
    client = app.test_client()
    assert client.get("/assets/globe/globe.json").get_json() == {"version": 1}
    assert client.get("/assets/globe/missing.png").status_code == 404


def test_system_modes(client):
    for mode in ("earth-moon", "sun-moon-earth"):
        res = client.get(f"/system/{mode}")
        assert res.status_code == 200
        assert f'data-mode="{mode}"' in res.get_data(as_text=True)


def test_system_unknown_mode_falls_back(client):
    res = client.get("/system/unknown")
    assert 'data-mode="earth-moon"' in res.get_data(as_text=True)


def test_system_page_has_controls(client):
    html = client.get("/system/earth-moon").get_data(as_text=True)
    for marker in ('data-focus="moonview"', 'id="system-scale"', 'id="system-play"', "system-facts", "system_view.js"):
        assert marker in html


def test_system_assets_served_from_cache_dir(app, tmp_path):
    (tmp_path / "system").mkdir()
    (tmp_path / "system" / "system.json").write_text('{"version": 2}', encoding="utf-8")
    app.config["CACHE_DIR"] = tmp_path
    client = app.test_client()
    assert client.get("/assets/system/system.json").get_json() == {"version": 2}
    assert client.get("/assets/system/missing.glb").status_code == 404


def test_search_redirect_keeps_query_parameters(client):
    """Стара адреса /search веде на «Місяць» і зберігає дату, місце й мову (раніше ?lang=en губився)."""
    res = client.get("/search?lang=en&datetime=2027-07-01T00:00Z&lat=-85&lon=0")
    assert res.status_code == 302
    location = res.headers["Location"]
    assert location.startswith("/moon?") and location.endswith("#search")
    for part in ("lang=en", "datetime=2027-07-01T00:00Z", "lat=-85", "lon=0"):
        assert part in location
    assert client.get("/search").headers["Location"] == "/moon#search"
