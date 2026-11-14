"""Вкладка «Вікно запуску» (F7): сторінка, вкладка в меню, модуль і елементи керування."""


def test_launch_window_page(client):
    res = client.get("/launch-window")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    for marker in ("lw-form", "lw-site", "lw-trajectory", "lw-days", "lw-priorities", "lw-scale", "lw-table",
                   "launch_window.js", "calendar-input", "metrics-overlay"):
        assert marker in html, marker


def test_tab_is_in_navigation_and_active(client):
    html = client.get("/launch-window").get_data(as_text=True)
    assert 'href="/launch-window" class="active"' in html
    assert 'href="/launch-window"' in client.get("/moon").get_data(as_text=True)
