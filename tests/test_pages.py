def test_index_redirects_to_moon(client):
    res = client.get("/")
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/moon")


def test_moon_page(client):
    res = client.get("/moon")
    assert res.status_code == 200
    assert "calendar-input" in res.get_data(as_text=True)
    assert "metrics-overlay" in res.get_data(as_text=True)


def test_system_modes(client):
    for mode in ("earth-moon", "sun-moon-earth"):
        res = client.get(f"/system/{mode}")
        assert res.status_code == 200
        assert f'data-mode="{mode}"' in res.get_data(as_text=True)


def test_system_unknown_mode_falls_back(client):
    res = client.get("/system/unknown")
    assert 'data-mode="earth-moon"' in res.get_data(as_text=True)
