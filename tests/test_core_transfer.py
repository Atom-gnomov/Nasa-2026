"""M10: перехід Земля → Місяць за зшитими конічними перерізами (docs/MATH.md, §21.5)."""

import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.core import transfer as tr
from app.core.constants import R_EARTH_KM, R_MOON_KM
from app.core.orbits import GM_EARTH, GM_MOON

R0 = R_EARTH_KM + tr.DEFAULT_PARAMS.parking_altitude_km
R_MOON_ORBIT = 384_400.0


def _propagate(r, v, tof_s, mu=GM_EARTH, steps=20_000):
    """Еталон для перевірки Ламберта: чисельне інтегрування задачі двох тіл (RK4)."""
    y = np.concatenate([np.asarray(r, float), np.asarray(v, float)])
    h = tof_s / steps

    def rhs(s):
        rr = s[:3]
        return np.concatenate([s[3:], -mu * rr / np.linalg.norm(rr) ** 3])

    for _ in range(steps):
        k1 = rhs(y)
        k2 = rhs(y + h / 2 * k1)
        k3 = rhs(y + h / 2 * k2)
        k4 = rhs(y + h * k3)
        y = y + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
    return y[:3], y[3:]


def _circular_moon():
    return np.array([R_MOON_ORBIT, 0.0, 0.0]), np.array([0.0, math.sqrt(GM_EARTH / R_MOON_ORBIT), 0.0])


# --- задача Ламберта ------------------------------------------------------------------------------------------


def test_lambert_textbook_example():
    # Curtis, «Orbital Mechanics for Engineering Students», приклад 5.2
    v1, v2 = tr.lambert([5000, 10000, 2100], [-14600, 2500, 7000], 3600)
    assert v1 == pytest.approx([-5.9925, 1.9254, 3.2456], abs=1e-4)
    assert v2 == pytest.approx([-3.3125, -4.1966, -0.38529], abs=1e-4)


@pytest.mark.parametrize(
    ("r1", "r2", "tof_h"),
    [
        ([R0, 0, 0], [-300_000, 150_000, 20_000], 80.0),  # еліпс, кут > 90°
        ([R0, 0, 0], [-200_000, 50_000, 0], 20.0),  # швидкий переліт — гіпербола
        ([7000, 0, 0], [0, 9000, 1000], 0.6),  # короткий кут
    ],
)
def test_lambert_reaches_target(r1, r2, tof_h):
    v1, v2 = tr.lambert(r1, r2, tof_h * 3600)
    r_end, v_end = _propagate(r1, v1, tof_h * 3600)
    assert np.linalg.norm(r_end - np.asarray(r2, float)) < 1.0  # км
    assert np.linalg.norm(v_end - v2) < 1e-4  # км/с


def test_lambert_direction_of_motion():
    # той самий кут, але рух у протилежний бік (normal = −z) — довга дуга з іншою швидкістю
    v_pro, _ = tr.lambert([7000, 0, 0], [0, 9000, 0], 3000)
    v_long, _ = tr.lambert([7000, 0, 0], [0, 9000, 0], 30_000, normal=[0, 0, -1])
    assert v_pro[1] > 0
    assert v_long[1] < 0
    r_end, _ = _propagate([7000, 0, 0], v_long, 30_000)
    assert np.linalg.norm(r_end - np.array([0, 9000, 0])) < 1.0


def test_lambert_rejects_bad_input():
    with pytest.raises(ValueError):
        tr.lambert([7000, 0, 0], [9000, 0, 0], 1000)  # кут 0°
    with pytest.raises(ValueError):
        tr.lambert([7000, 0, 0], [-9000, 0, 0], 1000)  # кут 180°
    with pytest.raises(ValueError):
        tr.lambert([7000, 0, 0], [0, 9000, 0], 0)


# --- окремі ділянки ------------------------------------------------------------------------------------------


def test_hohmann_reference_numbers():
    # MATH §13: імпульс розгону з НОО ~3,1–3,2 км/с, переліт ~3–5 діб
    dv, days = tr.hohmann_dv_m_s(R0, R_MOON_ORBIT)
    assert dv == pytest.approx(3135, abs=2)
    assert days == pytest.approx(4.98, abs=0.01)


def test_loi_from_rest_and_growth():
    r = R_MOON_KM + 100.0
    expected = 1000 * (math.sqrt(2 * GM_MOON / r) - math.sqrt(GM_MOON / r))
    assert float(tr.loi_dv_m_s(0.0)) == pytest.approx(expected)
    dv = tr.loi_dv_m_s([0.5, 0.8, 1.0])
    assert np.all(np.diff(dv) > 0)


# --- перехід у площині орбіти Місяця --------------------------------------------------------------------------


def test_transfer_matches_hohmann_limit():
    r_m, v_m = _circular_moon()
    dv_h, t_h = tr.hohmann_dv_m_s(R0, R_MOON_ORBIT)
    p = tr.coplanar_transfer(r_m, v_m, t_h)
    assert p.dv_tli_m_s == pytest.approx(dv_h, abs=3)
    # C3 гомановського еліпса: −μ/a
    assert p.c3_km2_s2 == pytest.approx(-GM_EARTH / ((R0 + R_MOON_ORBIT) / 2), abs=0.01)
    assert p.dv_total_m_s == pytest.approx(p.dv_tli_m_s + p.dv_loi_m_s)
    assert p.min_parking_inclination_deg == pytest.approx(0.0, abs=1e-9)


def test_faster_transfer_costs_more_fuel():
    r_m, v_m = _circular_moon()
    tli = [tr.coplanar_transfer(r_m, v_m, t).dv_tli_m_s for t in (1.5, 2.0, 3.0, 4.0)]
    assert np.all(np.diff(tli) < 0)
    assert tli[0] - tli[-1] > 150  # «швидше → дорожче» помітно


def test_transfer_rejects_bad_time():
    r_m, v_m = _circular_moon()
    with pytest.raises(ValueError):
        tr.coplanar_transfer(r_m, v_m, 0)


def test_inclination_follows_moon_declination():
    r = np.array([R_MOON_ORBIT * math.cos(math.radians(20)), 0.0, R_MOON_ORBIT * math.sin(math.radians(20))])
    v = np.array([0.0, math.sqrt(GM_EARTH / R_MOON_ORBIT), 0.0])
    p = tr.coplanar_transfer(r, v, 4.0)
    assert p.min_parking_inclination_deg == pytest.approx(20.0, abs=1e-6)


# --- з ефемеридами DE440 --------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def eph():
    pytest.importorskip("naif_de440")
    from app.core.ephemeris import get_ephemeris

    return get_ephemeris()


def test_curve_with_ephemeris(eph):
    dep = datetime(2027, 7, 1, tzinfo=timezone.utc)
    curve = tr.dv_curve(eph, dep, [3.0, 4.0, 5.0])
    for p in curve:
        assert p.departure_utc == dep
        assert p.arrival_utc == dep + timedelta(days=p.tof_days)
        assert 3100 < p.dv_tli_m_s < 3200  # MATH §13
        assert 356_000 < p.moon_distance_km < 407_000
        assert 0 <= p.min_parking_inclination_deg <= 29.0  # схилення Місяця ≤ 28,6° (MATH §13)


def test_transfer_options(eph):
    dep = datetime(2027, 7, 1, 6, 30)  # без часової зони — UTC
    opts = tr.transfer_options(eph, dep)
    direct, low = opts["direct"], opts["low_energy"]

    assert direct.method == "patched_conic"
    assert direct.duration_days == (3.0, 5.0)
    assert direct.arrival_utc[0] == datetime(2027, 7, 4, 6, 30, tzinfo=timezone.utc)
    assert 3100 < direct.dv_tli_m_s[0] <= direct.dv_tli_m_s[1] < 3200
    assert direct.dv_total_m_s[0] == pytest.approx(direct.best.dv_total_m_s)

    assert low.method == "estimate"
    assert low.dv_tli_m_s is None and low.best is None
    save_min, save_max = tr.LOW_ENERGY_DV_SAVING_M_S
    assert low.dv_total_m_s == pytest.approx((direct.best.dv_total_m_s - save_max,
                                              direct.best.dv_total_m_s - save_min))
    assert low.arrival_utc[0] - dep.replace(tzinfo=timezone.utc) == timedelta(days=low.duration_days[0])
