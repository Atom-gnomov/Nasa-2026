"""M19: Δv з майданчика — азимут, нахил, вікна, доворот площини (docs/MATH.md, §21.2–21.4)."""

import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.core import launch as ln

START = datetime(2027, 7, 1, tzinfo=timezone.utc)


# --- азимут і нахил ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("lat", [0.0, 5.2, 28.5, -35.0, 51.9])
def test_east_launch_gives_inclination_equal_to_latitude(lat):
    assert ln.inclination_from_azimuth_deg(lat, 90.0) == pytest.approx(abs(lat), abs=1e-9)
    a1, a2 = ln.azimuths_for_inclination_deg(lat, abs(lat))
    assert a1 == pytest.approx(90.0, abs=1e-6) and a2 == pytest.approx(90.0, abs=1e-6)


def test_azimuths_roundtrip_and_unreachable():
    a1, a2 = ln.azimuths_for_inclination_deg(28.5, 51.6)
    assert a1 < 90 < a2 and a1 + a2 == pytest.approx(180.0)
    for a in (a1, a2):
        assert ln.inclination_from_azimuth_deg(28.5, a) == pytest.approx(51.6, abs=1e-9)
    assert ln.azimuths_for_inclination_deg(45.9, 28.6) is None  # i < |φ|


def test_rotation_gain_equator_east():
    assert ln.rotation_gain_m_s(0.0, 90.0) == pytest.approx(465.1)
    assert ln.rotation_gain_m_s(28.5, 90.0) == pytest.approx(408.7, abs=0.1)  # MATH §13
    assert ln.rotation_gain_m_s(0.0, 270.0) == pytest.approx(-465.1)  # старт на захід втрачає


def test_gain_depends_only_on_inclination():
    # v_оберт·cos φ·sin A = 465,1·cos i для будь-якого майданчика, що досягає нахилу i
    for lat in (0.0, 13.7, 28.5):
        a, _ = ln.azimuths_for_inclination_deg(lat, 40.0)
        assert ln.rotation_gain_m_s(lat, a) == pytest.approx(465.1 * math.cos(math.radians(40.0)), abs=1e-6)


def test_ground_azimuth():
    assert ln.ground_azimuth_deg(0.0, 90.0) == pytest.approx(90.0)
    # обертання Землі «зносить» схід: відносно Землі ракета йде північніше за інерційний азимут
    assert ln.ground_azimuth_deg(28.5, 45.0) < 45.0
    assert ln.ground_azimuth_deg(28.5, 135.0) > 135.0


def test_plane_change_per_degree():
    assert ln.plane_change_dv_m_s(7800, 1.0) == pytest.approx(136.1, abs=0.1)  # TASKS M19, MATH §21.4


# --- site_departure -----------------------------------------------------------------------------------------


def test_departure_two_windows_without_plane_change():
    d = ln.site_departure(28.5, 40.0)
    assert d.windows_per_day == 2
    assert d.plane_change_deg == 0.0 and d.plane_change_dv_m_s == 0.0
    assert d.launch_inclination_deg == pytest.approx(40.0)
    assert d.rotation_gain_m_s == pytest.approx(465.1 * math.cos(math.radians(40.0)))
    assert d.dv_penalty_m_s == pytest.approx(465.1 - d.rotation_gain_m_s)


def test_departure_equator_is_ideal():
    d = ln.site_departure(0.0, 0.0)
    assert d.windows_per_day == 1
    assert d.rotation_gain_m_s == pytest.approx(465.1)
    assert d.dv_penalty_m_s == pytest.approx(0.0, abs=1e-9)


def test_departure_needs_plane_change_from_high_latitude():
    d = ln.site_departure(51.9, 28.6)  # Восточний → площина з нахилом 28,6°
    assert d.windows_per_day == 0
    assert d.launch_inclination_deg == pytest.approx(51.9)
    assert d.plane_change_deg == pytest.approx(23.3)
    assert d.plane_change_dv_m_s == pytest.approx(ln.plane_change_dv_m_s(ln.PARKING_ORBIT_SPEED_M_S, 23.3))
    assert d.plane_change_dv_m_s > 3000  # доворот дорожчий за будь-яку прибавку від обертання


def test_departure_azimuth_limits():
    one = ln.site_departure(28.5, 51.6, azimuth_limits_deg=(35.0, 120.0))
    assert one.azimuth_limited and one.windows_per_day == 1
    assert one.inertial_azimuths_deg[0] < 90

    none = ln.site_departure(28.5, 51.6, azimuth_limits_deg=(100.0, 120.0))
    assert none.azimuth_limited and none.windows_per_day == 0
    assert none.inertial_azimuths_deg == (120.0,)  # найближчий до південно-східного азимуту
    assert none.launch_inclination_deg == pytest.approx(ln.inclination_from_azimuth_deg(28.5, 120.0))
    assert none.plane_change_deg == pytest.approx(abs(none.launch_inclination_deg - 51.6))


def test_departure_rejects_bad_input():
    with pytest.raises(ValueError):
        ln.site_departure(90.0, 10.0)
    with pytest.raises(ValueError):
        ln.site_departure(10.0, 200.0)


def test_best_inclination():
    assert ln.best_inclination_deg(5.2, -23.0) == 23.0
    assert ln.best_inclination_deg(51.9, 18.3) == 51.9


# --- вікна запуску --------------------------------------------------------------------------------------------


def test_gmst_at_j2000():
    assert ln.gmst_deg(datetime(2000, 1, 1, 12, tzinfo=timezone.utc)) == pytest.approx(280.46061837)


def test_two_windows_per_day_in_plane():
    n = ln.plane_normal(28.6, 75.0)
    windows = ln.launch_windows(5.2, -52.8, n, START, days=3)
    assert len(windows) == 6
    for w in windows:
        r = ln.site_unit_vector(5.2, -52.8, w.time_utc)
        assert abs(float(n @ r)) < 1e-4  # майданчик у площині (з точністю до округлення до секунди)
    gaps = np.diff([w.time_utc.timestamp() for w in windows[::2]])
    assert gaps == pytest.approx([ln.SIDEREAL_DAY_S] * 2, abs=1.0)
    assert {w.direction for w in windows} == {"northeast", "southeast"}
    expected = ln.azimuths_for_inclination_deg(5.2, 28.6)
    for w in windows:
        assert min(abs(w.inertial_azimuth_deg - a) for a in expected) < 0.01


def test_no_window_when_latitude_above_inclination():
    n = ln.plane_normal(28.6, 75.0)
    assert ln.launch_windows(51.9, 128.3, n, START) == []
    assert ln.launch_windows(10.0, 0.0, [0.0, 0.0, 1.0], START) == []  # екваторіальна площина


def test_windows_within_period():
    n = ln.plane_normal(40.0, 10.0)
    end = START + timedelta(days=1)
    ws = ln.launch_windows(28.5, -80.6, n, START, days=1)
    assert len(ws) == 2 and all(START <= w.time_utc < end for w in ws)
