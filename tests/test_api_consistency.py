"""B23: POST /api/consistency — перевірка узгодженості виборів майстра (крок 9)."""

import pytest

from app.services import consistency, timeline
from tests.test_contracts import api_validator, assert_valid

DATE = "2027-08-24T02:01Z"
SITE = {"lat": -89.5, "lon": 0}
CREW = {"mission_profile": "crewed", "crew": 2, "days": 10}
CREW1 = {"mission_profile": "crewed", "days": 10}
MEMBERS = [{"sex": "male", "age": 35, "mass_kg": 82, "height_m": 1.78, "activity": "active"}]


def _fake_timeline(monkeypatch, **summary):
    base = {"sun_fraction": 0.6, "earth_fraction": 0.5, "longest_night_h": 0.0, "comm_fraction": 0.5}
    monkeypatch.setattr(timeline, "timeline", lambda *a, **k: {"summary": {**base, **summary}})


def _post(client, body):
    res = client.post("/api/consistency", json=body)
    assert res.status_code == 200, res.get_json()
    data = res.get_json()
    assert_valid(api_validator("ConsistencyResponse"), data)
    return data


def _ids(data, severity=None):
    return {c["id"] for c in data["conflicts"] if severity in (None, c["severity"])}


def test_clean_plan_has_no_warnings(client, monkeypatch):
    _fake_timeline(monkeypatch)
    data = _post(
        client,
        {"mission": {"days": 0}, "datetime": DATE, "site": SITE, "goal": "ice", "name": "Південь", "stay_days": 7},
    )
    assert data["ok"] is True
    assert data["counts"] == {"error": 0, "warning": 0, "info": 0}
    assert data["conflicts"] == [] and data["skipped"] == []
    assert data["window"]["start"] > DATE  # приліт пізніше за старт
    assert data["steps_to_review"] == []


def test_missing_choices_point_to_their_steps(client):
    data = _post(client, {"mission": CREW})
    steps = {c["id"]: c["step"] for c in data["conflicts"]}
    assert steps["goal-missing"] == 1 and steps["name-missing"] == 1
    assert steps["window-missing"] == 3
    assert data["skipped"][0]["id"] == "light"
    data = _post(client, {"mission": CREW, "datetime": DATE})
    assert {c["id"]: c["step"] for c in data["conflicts"]}["site-missing"] == 5


def test_crewed_without_stay_days_and_supplies(client, monkeypatch):
    _fake_timeline(monkeypatch)
    data = _post(
        client,
        {
            "mission": {"mission_profile": "crewed", "crew": 2, "days": 0},
            "datetime": DATE,
            "site": SITE,
            "goal": "ice",
            "name": "x",
        },
    )
    assert "stay-missing" in _ids(data, "warning")
    assert "supplies-not-computed" in _ids(data, "info")


def test_supply_shortage_is_error_and_blocks_ok(client, monkeypatch):
    _fake_timeline(monkeypatch)
    mission = {**CREW1, "crew_members": MEMBERS, "supply_days": 1, "reserve_fraction": 0}
    data = _post(client, {"mission": mission, "datetime": DATE, "site": SITE, "goal": "ice", "name": "x"})
    err = [c for c in data["conflicts"] if c["id"] == "supplies-shortage"]
    assert err and err[0]["severity"] == "error" and err[0]["step"] == 6
    assert data["ok"] is False and 6 in data["steps_to_review"]


def test_capacity_exceeded_points_to_carrier(client, monkeypatch):
    _fake_timeline(monkeypatch)
    mission = {**CREW, "sizes": {"equipment": "max", "life_support": "max", "comfort": "max"}}
    data = _post(client, {"mission": mission, "datetime": DATE, "site": SITE, "goal": "ice", "name": "x"})
    cap = [c for c in data["conflicts"] if c["id"] == "capacity-exceeded"]
    assert cap and cap[0]["step"] == 8 and cap[0]["values"]["launches"] > 1


def test_no_sunlight_is_error_unless_reactor(client, monkeypatch):
    _fake_timeline(monkeypatch, sun_fraction=0.0, longest_night_h=240.0)
    base = {"mission": {"days": 0}, "datetime": DATE, "site": SITE, "goal": "ice", "name": "x", "stay_days": 7}
    data = _post(client, base)
    assert "light-none" in _ids(data, "error") and data["ok"] is False
    with_reactor = _post(
        client, {**base, "mission": {"days": 0, "equipment_items": [{"id": "fsp_reactor", "count": 1}]}}
    )
    assert "light-none" in _ids(with_reactor, "warning")
    assert "night-underestimated" not in _ids(with_reactor)  # реактор не залежить від ночі


def test_thresholds_come_from_profile_and_night_suggestion(client, monkeypatch):
    _fake_timeline(monkeypatch, sun_fraction=0.02, earth_fraction=0.1, longest_night_h=300.0)
    data = _post(client, {"mission": CREW, "datetime": DATE, "site": SITE, "goal": "ice", "name": "x"})
    by_id = {c["id"]: c for c in data["conflicts"]}
    assert (
        by_id["light-low"]["values"]["limit_percent"] == 5
        and by_id["light-low"]["values"]["limit_id"] == "sun-visibility-screening"
    )
    assert by_id["earth-low"]["values"]["limit_percent"] == 25
    assert by_id["night-underestimated"]["step"] == 7
    assert data["suggested"] == {"longest_night_h": 300.0}
    # якщо ніч у розрахунку вже врахована — зауваження зникає
    ok = _post(
        client,
        {"mission": {**CREW, "longest_night_h": 300}, "datetime": DATE, "site": SITE, "goal": "ice", "name": "x"},
    )
    assert "night-underestimated" not in _ids(ok) and ok["suggested"] == {}


def test_uncrewed_has_no_profile_thresholds(client, monkeypatch):
    _fake_timeline(monkeypatch, sun_fraction=0.02, earth_fraction=0.1)
    data = _post(
        client, {"mission": {"days": 0}, "datetime": DATE, "site": SITE, "goal": "ice", "name": "x", "stay_days": 5}
    )
    assert not ({"light-low", "earth-low"} & _ids(data))


def test_missing_ephemeris_skips_light(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("Немає ефемерид")

    monkeypatch.setattr(timeline, "timeline", boom)
    data = _post(client, {"mission": CREW, "datetime": DATE, "site": SITE, "goal": "ice", "name": "x"})
    assert data["skipped"] == [{"id": "light", "reason": "Немає ефемерид"}]


def test_sorted_by_severity_then_step(client, monkeypatch):
    _fake_timeline(monkeypatch, sun_fraction=0.0)
    data = _post(
        client,
        {
            "mission": {**CREW1, "crew_members": MEMBERS, "supply_days": 1, "reserve_fraction": 0},
            "datetime": DATE,
            "site": SITE,
        },
    )
    rank = {"error": 0, "warning": 1, "info": 2}
    keys = [(rank[c["severity"]], c["step"]) for c in data["conflicts"]]
    assert keys == sorted(keys)


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"nope": 1},
        {"mission": 5},
        {"datetime": "вчора"},
        {"datetime": 5},
        {"site": 5},
        {"site": {"lat": 100, "lon": 0}},
        {"site": {"lat": "x", "lon": 0}},
        {"stay_days": -1},
        {"stay_days": True},
        {"mission": {"crew": 99}},
    ],
)
def test_bad_requests_are_400(client, body):
    res = client.post("/api/consistency", json=body)
    assert res.status_code == 400
    assert_valid(api_validator("Error"), res.get_json())


def test_unknown_launch_site_is_404(client):
    res = client.post("/api/consistency", json={"mission": {"launch_site_id": "нема-такого"}})
    assert res.status_code == 404


def test_real_timeline_end_to_end(client):
    pytest.importorskip("naif_de440")
    res = client.post(
        "/api/consistency",
        json={"mission": {"days": 0}, "datetime": DATE, "site": SITE, "goal": "ice", "name": "x", "stay_days": 3},
    )
    if res.status_code == 503:
        pytest.skip("Немає ефемерид у цьому середовищі")
    data = res.get_json()
    assert_valid(api_validator("ConsistencyResponse"), data)
    assert data["window"]["longest_night_h"] >= 0


def test_service_rejects_non_object():
    with pytest.raises(consistency.ConsistencyError):
        consistency.compute([])
