"""B24: POST /api/report — підсумковий звіт місії (крок 10)."""

import pytest

from app.services import timeline
from tests.test_contracts import api_validator, assert_valid

DATE = "2027-08-24T02:01Z"
SITE = {"lat": -89.5, "lon": 0, "name": "Шеклтон"}
MEMBERS = [{"sex": "male", "age": 35, "mass_kg": 82, "height_m": 1.78, "activity": "active"}]


def _fake_timeline(monkeypatch, **summary):
    base = {"sun_fraction": 0.6, "earth_fraction": 0.5, "longest_night_h": 20.0, "comm_fraction": 0.5}
    monkeypatch.setattr(timeline, "timeline", lambda *a, **k: {"summary": {**base, **summary}})


def _post(client, body):
    res = client.post("/api/report", json=body)
    assert res.status_code == 200, res.get_json()
    data = res.get_json()
    assert_valid(api_validator("ReportResponse"), data)
    return data


def _values(data, step):
    return {r["label"]: r["value"] for s in data["sections"] if s["step"] == step for r in s["rows"]}


FULL = {
    "mission": {
        "mission_profile": "crewed",
        "days": 10,
        "crew_members": MEMBERS,
        "launch_system_id": "sls-block-1",
        "equipment_items": [{"id": "viper_rover", "count": 1}],
    },
    "datetime": DATE,
    "site": SITE,
    "goal": "ice",
    "name": "Південь-1",
}


def test_full_report_has_sections_in_step_order(client, monkeypatch):
    _fake_timeline(monkeypatch)
    data = _post(client, FULL)
    assert [s["step"] for s in data["sections"]] == [1, 2, 4, 5, 6, 7, 8, 9]
    assert data["name"] == "Південь-1" and data["goal_label"] == "Пошук води й льоду"
    assert _values(data, 1) == {"Назва": "Південь-1", "Мета": "Пошук води й льоду"}
    assert _values(data, 2)["Тип"] == "пілотована"
    assert _values(data, 5)["Дата посадки"] == "2027-08-24 02:01 UTC"  # дата й місце посадки — один крок
    assert "Шеклтон" in _values(data, 5)["Точка"]
    assert _values(data, 4)["Зліт і повернення"].startswith("не змодельовано")
    assert any("VIPER" in label for label in _values(data, 6))
    assert "кг" in _values(data, 7)["Маса на Місяці"]
    assert _values(data, 8)["Носій"] and _values(data, 8)["Ризик невдачі"]
    assert data["chain"][0] == "Назва місії" and data["chain"][-1] == "Підсумковий звіт"


def test_markdown_follows_sections_and_lists_sources(client, monkeypatch):
    _fake_timeline(monkeypatch)
    md = _post(client, FULL)["markdown"]
    assert md.startswith("# Місія: Південь-1")
    positions = [md.index(f"## {n}. ") for n in range(1, 9)]  # 8 розділів: «Дата посадки» злито з районом і точкою
    assert positions == sorted(positions)
    assert "## Послідовність рішень" in md and "Назва місії → Мета місії" in md
    assert "## Джерела" in md and "https://" in md  # VIPER має джерело NASA
    assert "тимчасові" in md


def test_sources_include_thresholds_used_by_conflicts(client, monkeypatch):
    _fake_timeline(monkeypatch, sun_fraction=0.02, earth_fraction=0.1)
    data = _post(client, {**FULL, "mission": {"mission_profile": "crewed", "days": 10, "crew_members": MEMBERS}})
    assert {c["id"] for c in data["conflicts"]} >= {"light-low", "earth-low"}
    assert any("Artemis" in s["title"] for s in data["sources"])


def test_empty_choices_still_give_a_report(client):
    data = _post(client, {"mission": {"days": 0}})
    assert _values(data, 1) == {"Назва": "не задано", "Мета": "не задано"}
    assert _values(data, 5)["Дата посадки"] == "не задано"
    assert _values(data, 5)["Точка"] == "не вибрано"
    assert data["markdown"].startswith("# Місія: без назви")
    assert data["ok"] is True


def test_uncrewed_report_has_no_crew_rows(client):
    data = _post(client, {"mission": {"days": 0}, "name": "Робот"})
    assert "Екіпаж" not in _values(data, 2)
    assert "Ризик втрати екіпажу" not in _values(data, 8)
    assert "Життєзабезпечення" not in _values(data, 7)


def test_report_matches_consistency_verdict(client, monkeypatch):
    _fake_timeline(monkeypatch, sun_fraction=0.0)
    body = {"mission": {"days": 0}, "datetime": DATE, "site": SITE, "goal": "ice", "name": "x", "stay_days": 5}
    check = client.post("/api/consistency", json=body).get_json()
    rep = client.post("/api/report", json=body).get_json()
    assert rep["ok"] is check["ok"] is False
    assert rep["conflicts"] == check["conflicts"]


@pytest.mark.parametrize(
    "body", [[], {"nope": 1}, {"mission": 5}, {"datetime": "вчора"}, {"site": {"lat": 100, "lon": 0}}]
)
def test_bad_requests_are_400(client, body):
    res = client.post("/api/report", json=body)
    assert res.status_code == 400
    assert_valid(api_validator("Error"), res.get_json())


def test_unknown_launch_site_is_404(client):
    assert client.post("/api/report", json={"mission": {"launch_site_id": "нема-такого"}}).status_code == 404
