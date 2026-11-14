import pytest

from app.core import risk
from app.core.risk import RiskParams, assess, band, landing_risk, launch_risk, systems_risk

SIZES = {"equipment": 0.5, "life_support": 0.5, "comfort": 0.5}


def test_launch_risk_at_utilization_half_one_and_one_and_a_half():
    # MATH.md §20: u = 0,5 / 1 / 1,5
    p_half, n_half = launch_risk(0.5)
    p_one, n_one = launch_risk(1.0)
    p_over, n_over = launch_risk(1.5)
    assert (p_half, n_half) == (pytest.approx(0.02), 1)  # далеко від межі — база
    assert (p_one, n_one) == (pytest.approx(0.04), 1)  # при u = 1 ризик подвоюється
    assert n_over == 2
    # два пуски по u = 0,75 (база 0,02 кожен) і одне стикування 0,01
    assert p_over == pytest.approx(1 - (0.98 ** 2) * 0.99)
    assert p_half < p_one < p_over


def test_launch_risk_starts_growing_only_near_the_limit():
    assert launch_risk(0.0)[0] == pytest.approx(0.02) == launch_risk(0.85)[0]
    assert 0.02 < launch_risk(0.92)[0] < launch_risk(0.99)[0] < launch_risk(1.0)[0]


def test_many_launches_raise_risk_further():
    assert launch_risk(3.5)[1] == 4 and launch_risk(3.5)[0] > launch_risk(1.5)[0]
    with pytest.raises(ValueError):
        launch_risk(-0.1)


def test_landing_risk_grows_with_mass_and_equals_base_at_reference():
    assert landing_risk(1000.0) == pytest.approx(0.20)
    assert landing_risk(500) < landing_risk(1000) < landing_risk(4000)
    assert landing_risk(4000) == pytest.approx(0.20 * 4 ** 0.4)
    assert landing_risk(1e12) == 0.95 and landing_risk(0) == 0.0
    with pytest.raises(ValueError):
        landing_risk(-1)


def test_systems_risk_grows_with_complexity():
    assert systems_risk(0.0) == pytest.approx(0.01) and systems_risk(1.0) == pytest.approx(0.05)
    with pytest.raises(ValueError):
        systems_risk(1.5)


def test_total_is_combination_of_independent_failures():
    a = assess(0.5, 1000.0, SIZES, crew=0)
    expected = 1 - (1 - a.p_launch) * (1 - a.p_transit) * (1 - a.p_landing) * (1 - a.p_systems)
    assert a.p_total == pytest.approx(expected)
    lo, hi = a.p_total_range
    assert lo < a.p_total < hi <= 1.0
    assert a.band == band(a.p_total) and a.band_label == risk.BAND_LABELS[a.band]


def test_uncrewed_has_no_crew_loss_and_only_equipment_drives_complexity():
    a = assess(0.5, 800.0, {"equipment": 0.0, "life_support": 1.0, "comfort": 1.0}, crew=0)
    assert a.p_crew_loss is None and a.p_crew_loss_range is None and a.crew_band is None
    assert a.p_systems == pytest.approx(0.01)  # life_support і comfort ігноруються


def test_crew_loss_is_part_of_total_failure_and_reacts_to_redundancy_and_trajectory():
    base = assess(0.5, 3000.0, {"equipment": 0.5, "life_support": 0.0, "comfort": 0.5}, crew=4)
    redundant = assess(0.5, 3000.0, {"equipment": 0.5, "life_support": 1.0, "comfort": 0.5}, crew=4)
    slow = assess(0.5, 3000.0, {"equipment": 0.5, "life_support": 0.0, "comfort": 0.5}, crew=4, trajectory="low_energy")
    assert 0 < base.p_crew_loss < base.p_total
    assert base.p_crew_loss == pytest.approx(base.p_total * 0.5)
    # більше резервування знижує ризик для екіпажу, але складність систем підвищує загальний ризик
    assert redundant.p_crew_loss < base.p_crew_loss and redundant.p_systems > base.p_systems
    assert slow.p_crew_loss > base.p_crew_loss
    assert base.crew_band in ("low", "moderate", "high", "very_high") and base.crew_band_label


def test_heavier_and_fuller_missions_are_riskier():
    light = assess(0.4, 500.0, SIZES, crew=0)
    heavy = assess(0.4, 5000.0, SIZES, crew=0)
    full = assess(0.99, 500.0, SIZES, crew=0)
    assert heavy.p_total > light.p_total and full.p_total > light.p_total


@pytest.mark.parametrize("p, expected", [(0.0, "low"), (0.0499, "low"), (0.05, "moderate"), (0.1499, "moderate"),
                                         (0.15, "high"), (0.3499, "high"), (0.35, "very_high"), (1.0, "very_high")])
def test_verbal_scale_boundaries(p, expected):
    assert band(p) == expected


def test_range_is_clipped_to_probability():
    params = RiskParams(uncertainty=(0.5, 50.0))
    a = assess(0.5, 5000.0, SIZES, params=params)
    assert a.p_total_range[1] == 1.0


@pytest.mark.parametrize("kwargs", [
    {"trajectory": "warp"}, {"crew": -1}, {"crew": 1.5}, {"crew": True}, {"sizes": {"equipment": 2.0}},
])
def test_validation(kwargs):
    args = {"utilization": 0.5, "mass_moon_kg": 100.0, "sizes": SIZES, **kwargs}
    with pytest.raises(ValueError):
        assess(**args)
    with pytest.raises(ValueError):
        band(1.5)
