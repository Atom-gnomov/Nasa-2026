"""Система запуску замість «типової ракети» (app/core/launch_system.py, M18)."""

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
    assert choice.provisional_fields == ("price_usd_per_kg", "failure_probability")


def test_explicit_price_and_failure_are_not_provisional():
    choice = ls.to_rocket(_system("ariane-64"), price_usd_per_kg=(3000.0, 4000.0), failure_probability=0.05)
    assert choice.rocket.price_usd_per_kg == (3000.0, 4000.0) and choice.rocket.failure_probability == 0.05
    assert choice.provisional_fields == ()
    only_price = ls.to_rocket(_system("ariane-64"), price_usd_per_kg=(3000.0, 4000.0))
    assert only_price.provisional_fields == ("failure_probability",)


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
