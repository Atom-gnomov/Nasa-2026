"""Система запуску замість «типової ракети» (app/core/launch_system.py, M18)."""

import dataclasses
import json
from pathlib import Path

import pytest

from app.core import cost, launch_system as ls, risk

CATALOG = json.loads(
    (Path(__file__).resolve().parents[1] / "app" / "data" / "launch_systems.json").read_text(encoding="utf-8"))


def _system(system_id: str) -> ls.LaunchSystem:
    return ls.from_catalog(next(r for r in CATALOG if r["id"] == system_id))


def test_every_catalog_row_converts_and_keeps_only_published_values():
    systems = [ls.from_catalog(r) for r in CATALOG]
    assert {s.kind for s in systems} == set(ls.KINDS)
    pegasus = _system("pegasus-xl")
    assert pegasus.capacity_leo_kg == pytest.approx(453.59) and pegasus.drop_altitude_m == 12192
    assert pegasus.launch_site_ids == ()
    zenit = _system("zenit-3sl-sea-launch")
    assert zenit.capacity_leo_kg is None  # у джерелах лише ГПО — НОО не вигадуємо
    assert zenit.kind == "sea_platform" and zenit.launch_site_ids


def test_to_rocket_uses_catalog_capacity_and_lists_provisional_fields():
    choice = ls.to_rocket(_system("ariane-64"))
    assert choice.rocket.capacity_leo_kg == 21600.0 and choice.rocket.name.startswith("Ariane 64")
    assert choice.rocket.price_usd_per_kg == cost.DEFAULT_ROCKET.price_usd_per_kg
    # D8: у каталозі є статистика польотів Ariane 64 (3 з 3 вдалі за GCAT) — база відмови вже не тимчасова
    assert choice.provisional_fields == ("price_usd_per_kg",)
    assert choice.rocket.failure_probability == pytest.approx(ls.failure_from_flights(3, 0)[0])


def test_explicit_price_and_failure_are_not_provisional():
    choice = ls.to_rocket(_system("ariane-64"), price_usd_per_kg=(3000.0, 4000.0), failure_probability=0.05)
    assert choice.rocket.price_usd_per_kg == (3000.0, 4000.0) and choice.rocket.failure_probability == 0.05
    assert choice.provisional_fields == ()
    only_price = ls.to_rocket(_system("ariane-64"), price_usd_per_kg=(3000.0, 4000.0))
    assert only_price.provisional_fields == ()  # відмова — зі статистики польотів каталогу (D8)
    no_stats = dataclasses.replace(_system("ariane-64"), flights_total=None, flights_failed=None)
    assert ls.to_rocket(no_stats, price_usd_per_kg=(3000.0, 4000.0)).provisional_fields == ("failure_probability",)


def test_system_without_leo_capacity_is_rejected():
    with pytest.raises(ValueError, match="НОО"):
        ls.to_rocket(_system("zenit-3sl-sea-launch"))
    with pytest.raises(ValueError):
        ls.fit(1000.0, _system("zenit-3sl-sea-launch"))


def test_smaller_rocket_means_higher_utilization_and_more_launches_in_cost_and_risk():
    mass_leo = 20_000.0
    big = ls.to_rocket(_system("ariane-64")).rocket
    small = ls.to_rocket(_system("ariane-62")).rocket  # 10 300 кг на НОО за каталогом
    assert cost.utilization(mass_leo, small) > cost.utilization(mass_leo, big)
    assert cost.launches_needed(mass_leo, small) > cost.launches_needed(mass_leo, big)
    masses = {"equipment": 400.0, "structure": 300.0, "margin": 100.0}
    est_big = cost.mission_cost(masses, rocket=big)
    est_small = cost.mission_cost(masses, rocket=small)
    assert est_small.utilization > est_big.utilization
    sizes = {"equipment": 0.5, "life_support": 0.0, "comfort": 0.0}
    risk_big = risk.assess(est_big.utilization, est_big.mass_moon_kg, sizes)
    risk_small = risk.assess(est_small.utilization, est_small.mass_moon_kg, sizes)
    assert risk_small.p_launch >= risk_big.p_launch


def test_fit_flags_air_launch_that_cannot_carry_a_lunar_lander():
    air = _system("pegasus-xl")
    result = ls.fit(5_000.0, air)
    assert result["utilization"] > 1 and result["launches"] == 12 and not result["fits_single_launch"]
    assert "літака-носія" in result["note"]
    ground = ls.fit(5_000.0, _system("ariane-64"))
    assert ground["fits_single_launch"] and ground["launches"] == 1 and ground["note"] is None
    multi = ls.fit(50_000.0, _system("ariane-64"))
    assert multi["launches"] == 3 and "стикування" in multi["note"]


def test_unknown_kind_is_rejected():
    row = dict(next(r for r in CATALOG if r["id"] == "pegasus-xl"), kind="balloon")
    with pytest.raises(ValueError):
        ls.from_catalog(row)


def test_to_dict_is_serialisable():
    json.dumps(ls.to_rocket(_system("pegasus-xl")).to_dict())


def test_catalog_loader_gives_the_same_rows(app):
    from app.services import catalogs

    with app.app_context():
        rows = catalogs.load_launch_systems()
    assert [r["id"] for r in rows] == [r["id"] for r in CATALOG]


# ---------- M21: економіка з каталогу (D8) на синтетичних фактах ----------
def _fact_row(**facts):
    """Рядок каталогу з місткістю 20 000 кг і заданими фактами (синтетичний, не дані про реальну ракету)."""
    base = {"id": "synthetic", "name": "Синтетична ракета", "kind": "spaceport", "active": True,
            "launch_site_ids": ["kourou"], "facts": []}
    src = {"title": "t", "ref": "r", "url": "https://example.org", "kind": "primary"}
    for quantity, value in {"capacity_leo_kg": 20000, **facts}.items():
        base["facts"].append({"quantity": quantity, "value": value, "source": src, "quote": "синтетична цитата тесту"})
    return base


def test_failure_from_flights_uses_laplace_rule_with_wilson_range():
    p, (lo, hi) = ls.failure_from_flights(100, 2)
    assert p == pytest.approx(3 / 102)
    assert 0 <= lo < p < hi <= 1
    p0, (lo0, hi0) = ls.failure_from_flights(10, 0)
    assert p0 == pytest.approx(1 / 12) and lo0 == 0 and hi0 > p0  # навіть без невдач — не нуль
    few = ls.failure_from_flights(3, 0)[1]
    many = ls.failure_from_flights(300, 0)[1]
    assert (few[1] - few[0]) > (many[1] - many[0])  # мало польотів — широкий діапазон
    with pytest.raises(ValueError):
        ls.failure_from_flights(0, 0)
    with pytest.raises(ValueError):
        ls.failure_from_flights(5, 6)


def test_catalog_price_and_flight_stats_replace_provisional_values():
    system = ls.from_catalog(_fact_row(price_usd_per_kg_leo_min=1500, price_usd_per_kg_leo_max=2500,
                                       flights_total=200, flights_failed=3))
    assert system.price_usd_per_kg == (1500.0, 2500.0) and (system.flights_total, system.flights_failed) == (200, 3)
    choice = ls.to_rocket(system)
    assert choice.provisional_fields == ()  # усе з каталогу
    assert choice.rocket.price_usd_per_kg == (1500.0, 2500.0)
    assert choice.rocket.failure_probability == pytest.approx(4 / 202)
    assert choice.failure_range is not None and choice.failure_range[0] < choice.rocket.failure_probability
    assert choice.risk_params().p_launch_base == pytest.approx(4 / 202)
    assert system.to_dict()["failure_probability"] == pytest.approx(4 / 202)


def test_partial_data_keeps_only_the_missing_field_provisional():
    only_price = ls.to_rocket(ls.from_catalog(_fact_row(price_usd_per_kg_leo_min=1000, price_usd_per_kg_leo_max=2000)))
    assert only_price.provisional_fields == ("failure_probability",)
    only_stats = ls.to_rocket(ls.from_catalog(_fact_row(flights_total=50, flights_failed=1)))
    assert only_stats.provisional_fields == ("price_usd_per_kg",)
    half_price = ls.from_catalog(_fact_row(price_usd_per_kg_leo_min=1000))  # лише мінімум — ціни немає
    assert half_price.price_usd_per_kg is None
    zero_flights = ls.to_rocket(ls.from_catalog(_fact_row(flights_total=0, flights_failed=0)))
    assert "failure_probability" in zero_flights.provisional_fields  # статистики немає


def test_explicit_values_win_over_catalog():
    system = ls.from_catalog(_fact_row(price_usd_per_kg_leo_min=1500, price_usd_per_kg_leo_max=2500,
                                       flights_total=200, flights_failed=3))
    choice = ls.to_rocket(system, price_usd_per_kg=(10.0, 20.0), failure_probability=0.5)
    assert choice.rocket.price_usd_per_kg == (10.0, 20.0) and choice.rocket.failure_probability == 0.5
    assert choice.failure_range is None


@pytest.mark.parametrize("facts", [
    {"price_usd_per_kg_leo_min": 3000, "price_usd_per_kg_leo_max": 2000},
    {"price_usd_per_kg_leo_min": 0, "price_usd_per_kg_leo_max": 2000},
    {"flights_total": 5.5, "flights_failed": 0},
    {"flights_total": -1, "flights_failed": 0},
])
def test_invalid_catalog_economics_is_rejected(facts):
    with pytest.raises(ValueError):
        ls.from_catalog(_fact_row(**facts))


def test_more_failures_raise_launch_risk_in_the_model():
    reliable = ls.to_rocket(ls.from_catalog(_fact_row(flights_total=300, flights_failed=1)))
    shaky = ls.to_rocket(ls.from_catalog(_fact_row(flights_total=30, flights_failed=6)))
    sizes = {"equipment": 0.5, "life_support": 0.0, "comfort": 0.0}
    a = risk.assess(0.5, 1000.0, sizes, params=reliable.risk_params())
    b = risk.assess(0.5, 1000.0, sizes, params=shaky.risk_params())
    assert b.p_launch > a.p_launch and b.p_total > a.p_total
