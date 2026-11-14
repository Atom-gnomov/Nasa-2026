import math

import pytest

from app.core import cost
from app.core.cost import CostTable, Rocket, TransferParams, mass_leo, mass_ratio, mission_cost, site_factor

MASSES = {"equipment": 520.0, "life_support": 0.0, "comfort": 0.0, "power_system": 5.0,
          "structure": 131.0, "margin": 131.0}


def test_mass_ratios_match_math_doc_examples():
    # MATH.md §13/§20: ≈ 5,3 кг на НОО на 1 кг на Місяці (пряма) і ≈ 4,8 (найекономніша), з інертною масою 10 %
    assert mass_ratio("direct") == pytest.approx(5.34, abs=0.02)
    assert mass_ratio("low_energy") == pytest.approx(4.83, abs=0.02)
    assert mass_ratio("low_energy") < mass_ratio("direct")


def test_mass_ratio_by_hand_for_one_stage():
    # без інертної маси й без розгону: лише посадка, e^{2700/(9,80665·320)}
    p = TransferParams(dv_tli_m_s=0.0, inert_fraction=0.0)
    assert mass_ratio("direct", p) == pytest.approx(math.exp(2700 / (cost.G0 * 320)), rel=1e-9)


def test_mass_leo_is_linear_and_validated():
    assert mass_leo(1000, "direct") == pytest.approx(1000 * mass_ratio("direct"))
    assert mass_leo(0, "direct") == 0
    with pytest.raises(ValueError):
        mass_leo(-1, "direct")
    with pytest.raises(ValueError, match="траєкторія"):
        mass_ratio("warp")


def test_site_factor_orders_launch_sites_by_latitude():
    assert site_factor(0.0) == pytest.approx(1.0)
    assert site_factor(28.5) == pytest.approx(1.0176, abs=0.001)  # мис Канаверал
    assert 1.0 < site_factor(5.2) < site_factor(28.5) < site_factor(45.9) < site_factor(51.9)
    assert site_factor(-28.5) == pytest.approx(site_factor(28.5))
    with pytest.raises(ValueError):
        site_factor(95)


def test_launches_and_utilization():
    r = Rocket(capacity_leo_kg=10_000)
    assert cost.utilization(5_000, r) == 0.5 and cost.launches_needed(5_000, r) == 1
    assert cost.launches_needed(10_000, r) == 1 and cost.launches_needed(10_001, r) == 2
    assert cost.launches_needed(0, r) == 1


def test_mission_cost_components_sum_and_ranges():
    c = mission_cost(MASSES, "direct", latitude_deg=28.5)
    for a, b in (c.launch_usd, c.payload_usd, c.lander_usd, c.total_usd):
        assert 0 < a < b
    assert c.total_usd[0] == pytest.approx(c.launch_usd[0] + c.payload_usd[0] + c.lander_usd[0])
    assert c.total_usd[1] == pytest.approx(c.launch_usd[1] + c.payload_usd[1] + c.lander_usd[1])
    assert c.mass_moon_kg == pytest.approx(sum(MASSES.values()))
    assert c.mass_leo_kg == pytest.approx(c.mass_moon_kg * c.mass_ratio)
    assert c.flight_time_days == (3.0, 5.0) and c.launches == 1 and 0 < c.utilization < 1


def test_launch_cost_by_hand():
    rocket = Rocket(price_usd_per_kg=(1_000.0, 3_000.0), capacity_leo_kg=1e9)
    c = mission_cost({"equipment": 100.0}, "direct", latitude_deg=0.0, rocket=rocket)
    leo = 100 * mass_ratio("direct")
    assert c.launch_usd == pytest.approx((1_000 * leo, 3_000 * leo))


def test_heavier_payload_costs_more_and_equator_is_cheaper():
    light, heavy = mission_cost({"equipment": 100}), mission_cost({"equipment": 200})
    assert heavy.total_usd[0] > light.total_usd[0] and heavy.launch_usd[1] == pytest.approx(2 * light.launch_usd[1])
    assert mission_cost(MASSES, latitude_deg=0).launch_usd[0] < mission_cost(MASSES, latitude_deg=51.9).launch_usd[0]


def test_low_energy_launch_is_cheaper_but_flight_is_longer():
    d, e = mission_cost(MASSES, "direct"), mission_cost(MASSES, "low_energy")
    assert e.launch_usd[0] < d.launch_usd[0] and e.flight_time_days[0] > d.flight_time_days[1]


def test_multiple_launches_when_over_capacity():
    c = mission_cost({"equipment": 8_000.0}, "direct", rocket=Rocket(capacity_leo_kg=17_500))
    assert c.mass_leo_kg > 17_500 and c.launches == math.ceil(c.mass_leo_kg / 17_500) >= 3 and c.utilization > 2


def test_custom_tables_and_validation():
    table = CostTable(equipment_usd_per_kg=(1.0, 2.0), lander_usd_per_kg=(0.0, 0.0))
    c = mission_cost({"equipment": 10.0}, table=table, rocket=Rocket(price_usd_per_kg=(0.0, 0.0)))
    assert c.payload_usd == (10.0, 20.0) and c.total_usd == (10.0, 20.0)
    with pytest.raises(ValueError):
        mission_cost({"equipment": -1.0})
    with pytest.raises(ValueError):
        mission_cost(MASSES, "teleport")
    assert c.to_dict()["trajectory"] == "direct"
