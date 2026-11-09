import pytest

from app.services.comms import signal_delay_s
from app.services.horizon import SUN_ANGULAR_RADIUS_DEG, mask_elevation, visible_fraction


def test_signal_delay_mean_distance():
    # Середня відстань Земля–Місяць ~384 400 км → ~1,28 с
    assert signal_delay_s(384_400) == pytest.approx(1.282, abs=0.001)


def test_signal_delay_negative():
    with pytest.raises(ValueError):
        signal_delay_s(-1)


def test_point_visibility_without_mask():
    assert visible_fraction(1.0, 0.0) == 1.0
    assert visible_fraction(-1.0, 0.0) == 0.0


def test_mask_blocks_low_object():
    mask = [5.0] * 360
    assert visible_fraction(3.0, 90.0, mask) == 0.0
    assert visible_fraction(6.0, 90.0, mask) == 1.0


def test_sun_partial_disk():
    assert visible_fraction(0.0, 0.0, None, SUN_ANGULAR_RADIUS_DEG) == pytest.approx(0.5)


def test_mask_interpolation_wraps():
    mask = [0.0] * 360
    mask[359] = 10.0
    assert mask_elevation(mask, 359.5) == pytest.approx(5.0)
