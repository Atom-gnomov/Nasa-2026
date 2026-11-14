"""Спільні функції видимості (app/services/visibility.py, B1): збігаються з ендпоінтами й геометрією."""

from datetime import datetime, timezone

import pytest

pytest.importorskip("naif_de440")

from app.core.ephemeris import get_ephemeris  # noqa: E402
from app.core.horizon import SUN_ANGULAR_RADIUS_DEG, HorizonMask  # noqa: E402
from app.services import metrics, timeline, visibility  # noqa: E402

WHEN = datetime(2027, 7, 1, 12, 0, tzinfo=timezone.utc)
LAT, LON = 0.674, 23.473


def _flat_mask():
    return HorizonMask.flat()


def test_sun_and_earth_margins_follow_the_definition(app):
    eph = get_ephemeris()
    mask = _flat_mask()
    jd = float(eph.time(WHEN).tt)
    sun = eph.sun_track(eph.ts.tt_jd(jd), LAT, LON, 0.0)
    earth = eph.earth_track(eph.ts.tt_jd(jd), LAT, LON, 0.0)
    assert visibility.sun_margin_fn(eph, mask, LAT, LON)(jd) == pytest.approx(
        sun.elevation_deg + SUN_ANGULAR_RADIUS_DEG)
    assert visibility.earth_margin_fn(eph, mask, LAT, LON)(jd) == pytest.approx(earth.elevation_deg)


def test_mask_height_shifts_the_margin_one_to_one():
    eph = get_ephemeris()
    jd = float(eph.time(WHEN).tt)
    flat = visibility.sun_margin_fn(eph, _flat_mask(), LAT, LON)(jd)
    raised = visibility.sun_margin_fn(eph, HorizonMask.flat(value_deg=2.0), LAT, LON)(jd)
    assert flat - raised == pytest.approx(2.0)


def test_fractions_match_metrics_and_timeline(app):
    eph = get_ephemeris()
    mask = _flat_mask()
    _, _, sun_f, earth_f = visibility.sun_earth_visibility(eph, eph.time(WHEN), mask, LAT, LON)
    with app.app_context():
        m = metrics.site_metrics(LAT, LON, WHEN)
        tl = timeline.timeline(LAT, LON, WHEN, datetime(2027, 7, 2, 12, 0, tzinfo=timezone.utc), 6.0)
    assert m.sun_visible_fraction == pytest.approx(float(sun_f), abs=1e-3)
    assert m.earth_visible_fraction == pytest.approx(float(earth_f), abs=1e-3)
    assert tl["sun"]["visible_fraction"][0] == pytest.approx(float(sun_f), abs=1e-3)
    assert tl["earth"]["visible_fraction"][0] == pytest.approx(float(earth_f), abs=1e-3)


def test_station_margin_is_the_minimum_of_the_two_conditions(app):
    from app.services import dsn

    eph = get_ephemeris()
    jd = float(eph.time(WHEN).tt)
    with app.app_context():
        station = dsn.load_stations()[0]
    t = eph.ts.tt_jd(jd)
    from_moon = eph.station_track(t, LAT, LON, station.lat, station.lon, station.elevation_m, 0.0)
    from_earth = eph.moon_from_station(t, station.lat, station.lon, station.elevation_m)
    expected = min(float(from_moon.elevation_deg), float(from_earth.elevation_deg - station.min_elevation_deg))
    got = visibility.station_margin_fn(eph, _flat_mask(), LAT, LON, station)(jd)
    assert float(got) == pytest.approx(expected)
