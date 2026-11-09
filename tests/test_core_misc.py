import numpy as np
import pytest

from app.core import launch, power, radiation, scoring, stats, thermal
from app.core.constants import AU_KM
from app.core.horizon import HorizonMask


def test_stats():
    visible = np.array([1, 1, 0, 0, 0, 1, 0, 1, 1, 1], dtype=bool)
    assert stats.total_hours(visible, 2.0) == 12.0
    assert stats.fraction_of_time(visible) == pytest.approx(0.6)
    assert stats.longest_run_hours(~visible, 2.0) == 6.0
    assert stats.intervals(visible, np.arange(10)) == [(0, 1), (5, 5), (7, 9)]


def test_power_examples_from_math_doc():
    assert power.solar_irradiance(AU_KM) == pytest.approx(1361.0)
    assert power.panel_power_w(0.0, 1.0, AU_KM) == pytest.approx(408.3, abs=0.1)
    assert power.panel_power_w(1.5, 1.0, AU_KM, mode="horizontal") == pytest.approx(10.7, abs=0.1)
    with pytest.raises(ValueError):
        power.incidence_cosine(10, mode="diagonal")


def test_thermal_examples_from_math_doc():
    assert thermal.equilibrium_temperature_k(1.0) == pytest.approx(386, abs=1)
    assert thermal.equilibrium_temperature_k(np.sin(np.radians(1.5))) == pytest.approx(155, abs=1)


def test_radiation_crater_shielding():
    assert radiation.dose_rate_usv_per_day(HorizonMask.flat()) == pytest.approx(1369.0)
    assert radiation.dose_rate_usv_per_day(HorizonMask.flat(value_deg=15)) == pytest.approx(1369 * 0.741, abs=1)


def test_launch():
    assert launch.rotation_boost_m_s(0) == pytest.approx(465.1)
    assert launch.rotation_boost_m_s(28.5) == pytest.approx(408.7, abs=0.1)
    assert launch.plane_change_dv_m_s(7800, 1.0) == pytest.approx(136.1, abs=0.1)
    assert launch.min_inclination_deg(-35) == 35


def test_scoring():
    assert scoring.roc_weights(4) == pytest.approx([0.5208, 0.2708, 0.1458, 0.0625], abs=1e-4)
    assert scoring.roc_weights(4).sum() == pytest.approx(1.0)
    assert scoring.normalize([10, 20, 30]) == pytest.approx([0, 0.5, 1])
    assert scoring.normalize([10, 20, 30], higher_is_better=False) == pytest.approx([1, 0.5, 0])
    s = np.array([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5], [0.4, 0.4]])
    assert list(scoring.pareto_front(s)) == [0, 1, 2]
    assert scoring.maximin_score(s) == pytest.approx([0, 0, 50, 40])
    assert scoring.weighted_score(s, [0.75, 0.25]) == pytest.approx([75, 25, 50, 40])
