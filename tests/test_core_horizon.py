import numpy as np
import pytest

from app.core.horizon import HorizonMask, compute_mask, dip_deg, disk_fraction, horizon_distance_km


def test_dip_values_from_math_doc():
    assert dip_deg(2) == pytest.approx(0.087, abs=0.001)
    assert dip_deg(100) == pytest.approx(0.615, abs=0.001)
    assert horizon_distance_km(2) == pytest.approx(2.6, abs=0.05)


@pytest.mark.parametrize("k, expected", [(-1, 0.0), (-0.5, 0.196), (0, 0.5), (0.5, 0.804), (1, 1.0), (5, 1.0)])
def test_disk_fraction_segment(k, expected):
    assert disk_fraction(k, 0.0, 1.0) == pytest.approx(expected, abs=0.001)


def test_point_object_fraction():
    assert disk_fraction(0.1, 0.0, 0.0) == 1.0
    assert disk_fraction(-0.1, 0.0, 0.0) == 0.0


def test_mask_interpolation_wraps():
    m = np.zeros(360)
    m[359] = 10.0
    assert HorizonMask(m).at(359.5) == pytest.approx(5.0)


def test_sky_view_fraction():
    assert HorizonMask.flat().sky_view_fraction() == pytest.approx(1.0)
    assert HorizonMask.flat(value_deg=15).sky_view_fraction() == pytest.approx(1 - np.sin(np.radians(15)))


def test_compute_mask_flat_terrain_equals_dip():
    # Гладка сфера: найвища точка рельєфу — дотична, тобто −dip.
    mask = compute_mask(lambda la, lo: np.zeros(np.shape(la)), -60, 10, observer_height_m=10,
                        azimuth_step_deg=45, max_distance_km=20, min_step_km=0.005, step_growth=1.002)
    assert mask.elevations_deg == pytest.approx(-dip_deg(10), abs=0.01)


def test_compute_mask_ring_mountain_at_pole():
    # Кільце висотою 1 км на відстані ~30 км від полюса; працює на самому полюсі.
    ring_colat = 30 / 1737.4  # радіани
    def height(la, lo):
        colat = np.radians(90 + np.asarray(la))
        return np.where(np.abs(colat - ring_colat) < 0.5 / 1737.4, 1000.0, 0.0)
    mask = compute_mask(height, -90, 0, azimuth_step_deg=30, max_distance_km=60, min_step_km=0.05, step_growth=1.0)
    d = 30.0
    expected = np.degrees(np.arctan((1.0 - d**2 / (2 * 1737.4)) / d))
    assert mask.elevations_deg == pytest.approx(expected, abs=0.05)
