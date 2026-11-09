"""Регресійні тести М5: контрольні числа з docs/MATH.md, розділ 0."""

from datetime import datetime, timezone

import numpy as np
import pytest

pytest.importorskip("naif_de440")

from app.core import frames  # noqa: E402
from app.core.ephemeris import get_ephemeris  # noqa: E402


@pytest.fixture(scope="module")
def eph():
    return get_ephemeris()


@pytest.fixture(scope="module")
def year(eph):
    return eph.time_range(datetime(2027, 1, 1, tzinfo=timezone.utc), datetime(2028, 1, 1, tzinfo=timezone.utc), 2.0)


def test_libration_ranges(eph, year):
    lat, lon = frames.vector_to_latlon(eph.earth_vector_me(year))
    assert 6.5 < lat.max() < 7.1 and -7.1 < lat.min() < -6.5
    assert 7.3 < lon.max() < 8.3 and -8.3 < lon.min() < -7.3


def test_subsolar_latitude(eph, year):
    lat, _ = frames.vector_to_latlon(eph.sun_vector_me(year))
    assert np.abs(lat).max() == pytest.approx(1.55, abs=0.05)


def test_signal_delay_range(eph, year):
    d = np.linalg.norm(eph.earth_vector_me(year), axis=-1)
    delay = eph.signal_delay_s(d)
    assert delay.min() == pytest.approx(1.19, abs=0.01)
    assert delay.max() == pytest.approx(1.356, abs=0.01)


def test_south_pole_sun_and_earth(eph, year):
    sun = eph.sun_track(year, -90, 0)
    earth = eph.earth_track(year, -90, 0)
    assert np.abs(sun.elevation_deg).max() < 1.7
    assert np.abs(earth.elevation_deg).max() < 7.3
    assert 0.45 < np.mean(sun.elevation_deg > 0) < 0.56
    assert 0.45 < np.mean(earth.elevation_deg > 0) < 0.55


def test_near_side_vs_far_side_earth_visibility(eph, year):
    near = np.mean(eph.earth_track(year, -85, 0).elevation_deg > 0)
    far = np.mean(eph.earth_track(year, -85, 180).elevation_deg > 0)
    assert near == pytest.approx(0.76, abs=0.03)
    assert far == pytest.approx(0.22, abs=0.03)


def test_apollo_11_earth_always_up(eph, year):
    assert eph.earth_track(year, 0.674, 23.473).elevation_deg.min() > 55


def test_moon_from_goldstone(eph):
    t = eph.time_range(datetime(2027, 1, 1, tzinfo=timezone.utc), datetime(2027, 2, 1, tzinfo=timezone.utc), 1.0)
    alt = eph.moon_from_station(t, 35.4259, -116.8895, 1002).elevation_deg
    assert 0.3 < np.mean(alt > 10) < 0.5
