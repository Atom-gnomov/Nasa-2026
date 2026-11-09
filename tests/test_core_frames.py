import numpy as np
import pytest

from app.core import frames


def test_latlon_roundtrip():
    lat, lon = frames.vector_to_latlon(frames.latlon_to_vector(-45.0, 120.0, 1737.4))
    assert lat == pytest.approx(-45.0)
    assert lon == pytest.approx(120.0)


def test_enu_is_orthonormal_including_pole():
    for lat, lon in [(0, 0), (-45, 30), (-90, 0), (-90, 135), (89.9, -10)]:
        b = frames.enu_basis(lat, lon)
        assert b @ b.T == pytest.approx(np.eye(3), abs=1e-12)


def test_azel_zenith_and_horizon():
    b = frames.enu_basis(-30, 40)
    east, north, up = b
    assert frames.azel(up, b)[1] == pytest.approx(90.0)
    az, el = frames.azel(north, b)
    assert (az, el) == (pytest.approx(0.0), pytest.approx(0.0))
    az, el = frames.azel(east, b)
    assert (az, el) == (pytest.approx(90.0), pytest.approx(0.0))


def test_pole_grid_north_points_to_meridian():
    # На південному полюсі «північ» = напрямок на меридіан lon.
    north = frames.enu_basis(-90, 0)[1]
    assert north == pytest.approx([1.0, 0.0, 0.0], abs=1e-12)


def test_moon_rotation_is_proper_rotation():
    M = frames.icrf_to_moon_me(np.array([2451545.0, 2460000.5]))
    for m in M:
        assert m @ m.T == pytest.approx(np.eye(3), abs=1e-12)
        assert np.linalg.det(m) == pytest.approx(1.0)


def test_moon_rotation_rate_is_sidereal_month():
    # W зростає на 13,176°/добу → повний оберт за ~27,32 доби
    _, _, w0 = frames.iau_moon_angles(2460000.0)
    _, _, w1 = frames.iau_moon_angles(2460001.0)
    assert np.degrees(w1 - w0) == pytest.approx(13.176, abs=0.05)
