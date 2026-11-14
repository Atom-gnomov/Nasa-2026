"""Вкладка «План місії» (F16): сторінка, вкладка в меню, модуль і елементи керування."""


def test_plan_page(client):
    res = client.get("/plan")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    for marker in ("plan-form", "plan-profile", "plan-max-slope", "plan-vehicle", "plan-table", "plan.js",
                   "calendar-input", "metrics-overlay"):
        assert marker in html, marker


def test_tab_is_in_navigation_and_active(client):
    assert 'href="/plan" class="active"' in client.get("/plan").get_data(as_text=True)
    assert 'href="/plan"' in client.get("/moon").get_data(as_text=True)
