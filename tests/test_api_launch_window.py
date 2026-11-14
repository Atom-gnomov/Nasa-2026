"""GET /api/launch-window: контракт, оцінки дат, фактори, економна траєкторія, помилки (задача B8)."""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.core import scoring
from app.services import launch_window as lw
from tests.test_contracts import api_validator, assert_valid

URL = "/api/launch-window?launch_site=kourou&lat=-89.67&lon=129.78&start=2027-07-01&end=2027-07-30"


# --- чисті функції -------------------------------------------------------------------------------------------


def _day(dv, sun, earth, w):
    return {"dv_total_m_s": dv, "sun_fraction": sun, "earth_fraction": earth, "windows_per_day": w}


def test_score_days_roc_and_normalization():
    days = lw.score_days([_day(4000, 0.0, 1.0, 2), _day(3900, 1.0, 0.0, 1)], ["light", "fuel", "comms", "windows"])
    w = scoring.roc_weights(4)
    assert days[0]["factors"] == {"light": 0.0, "fuel": 0.0, "comms": 1.0, "windows": 1.0}
    assert days[1]["factors"] == {"light": 1.0, "fuel": 1.0, "comms": 0.0, "windows": 0.5}
    assert days[0]["score_pct"] == pytest.approx(100 * (w[2] + w[3]), abs=0.01)
    assert days[1]["score_pct"] == pytest.approx(100 * (w[0] + w[1] + 0.5 * w[3]), abs=0.01)


def test_priorities_change_the_best_day():
    raw = [_day(4000, 0.0, 1.0, 2), _day(3900, 1.0, 0.0, 2)]
    comms_first = lw.score_days([dict(d) for d in raw], ["comms", "light"])
    light_first = lw.score_days([dict(d) for d in raw], ["light", "comms"])
    assert comms_first[0]["score_pct"] > comms_first[1]["score_pct"]
    assert light_first[1]["score_pct"] > light_first[0]["score_pct"]


def test_parse_priorities():
    assert lw.parse_priorities(None) == list(lw.FACTORS)
    assert lw.parse_priorities("fuel, light") == ["fuel", "light"]
    for bad in ("fuel,fuel", "beauty", ","):
        with pytest.raises(ValueError):
            lw.parse_priorities(bad)


# --- API -----------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def window(app_module):
    pytest.importorskip("naif_de440")
    return app_module.test_client().get(URL).get_json()


@pytest.fixture(scope="module")
def app_module():
    from app import create_app
    from app.config import TestConfig

    return create_app(TestConfig)


def test_matches_contract_and_covers_period(window):
    assert_valid(api_validator("LaunchWindow"), window)
    days = window["days"]
    assert [d["date"] for d in days] == [(date(2027, 7, 1) + timedelta(days=i)).isoformat() for i in range(30)]
    assert window["method"] == "patched_conic"
    assert window["priorities"] == list(lw.FACTORS)


def test_best_day_is_the_highest_score(window):
    best = max(window["days"], key=lambda d: d["score_pct"])
    assert window["best"] == {"date": best["date"], "score_pct": best["score_pct"]}


def test_day_values_are_physical(window):
    for d in window["days"]:
        arrival = datetime.fromisoformat(d["arrival"].replace("Z", "+00:00"))
        departure = datetime.fromisoformat(d["date"]).replace(tzinfo=timezone.utc)
        assert 3.0 <= (arrival - departure).total_seconds() / 86400 <= 5.0
        assert 3900 < d["dv_total_m_s"] < 4200  # пряма: TLI ≈ 3,13 км/с + LOI ≈ 0,85 км/с + добавка Куру
        assert d["windows_per_day"] in (1, 2)
        assert 0 <= d["sun_fraction"] <= 1 and 0 <= d["earth_fraction"] <= 1
        assert set(d["factors"]) == set(lw.FACTORS)
    # за місячний місяць біля полюса є і темні, і освітлені прибуття
    light = [d["sun_fraction"] for d in window["days"]]
    assert min(light) < 0.2 and max(light) > 0.8


def test_low_energy_is_an_estimate(app_module):
    pytest.importorskip("naif_de440")
    res = app_module.test_client().get(URL.replace("2027-07-30", "2027-07-03") + "&trajectory=low_energy"
                                       "&priorities=fuel,light")
    data = res.get_json()
    assert res.status_code == 200 and data["method"] == "estimate"
    for d in data["days"]:
        assert d["flight_days"] == 105.0
        assert set(d["factors"]) == {"fuel", "light"}


@pytest.mark.parametrize(("query", "status"), [
    ("lat=0&lon=0&start=2027-07-01&end=2027-07-02", 400),
    ("launch_site=nope&lat=0&lon=0&start=2027-07-01&end=2027-07-02", 404),
    ("launch_site=kourou&lat=0&lon=0&start=2027-07-01", 400),
    ("launch_site=kourou&lat=95&lon=0&start=2027-07-01&end=2027-07-02", 400),
    ("launch_site=kourou&lat=0&lon=0&start=2027-07-05&end=2027-07-01", 400),
    ("launch_site=kourou&lat=0&lon=0&start=2027-07-01&end=2027-12-01", 400),
    ("launch_site=kourou&lat=0&lon=0&start=2027-07-01&end=2027-07-02&priorities=beauty", 400),
    ("launch_site=kourou&lat=0&lon=0&start=2027-07-01&end=2027-07-02&trajectory=warp", 400),
])
def test_errors(client, query, status):
    res = client.get("/api/launch-window?" + query)
    assert res.status_code == status
    assert_valid(api_validator("Error"), res.get_json())
