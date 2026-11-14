"""M20: ранжування майданчиків і ракет для вибраної точки Місяця (docs/MATH.md, §21.7)."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from app.core import launch_rank as lr

ROOT = Path(__file__).resolve().parents[1]

DIRECT = {"trajectory": "direct", "duration_days": (3.0, 5.0), "dv_tli_m_s": (3130.0, 3145.0),
          "dv_loi_m_s": (850.0, 910.0), "dv_total_m_s": (3980.0, 4055.0),
          "best": {"dv_tli_m_s": 3130.0, "min_parking_inclination_deg": 20.0}}
LOW = {"trajectory": "low_energy", "duration_days": (90.0, 120.0), "dv_tli_m_s": None, "dv_loi_m_s": None,
       "dv_total_m_s": (3580.0, 3880.0), "best": None}
TRANSFERS = {"direct": DIRECT, "low_energy": LOW}

SITES = [
    {"id": "eq", "name": "Екватор", "lat": 0.0, "lon": -154.0, "kind": "sea_platform"},
    {"id": "cape", "name": "Канаверал", "lat": 28.5, "lon": -80.6, "kind": "spaceport"},
    {"id": "air", "name": "Літак", "lat": 10.0, "lon": 0.0, "kind": "air_launch"},
]


def rocket(rid, sites, leo=None, tli=None, status="active", verified=True, moon_price=None):
    facts = []
    if leo:
        facts.append({"quantity": "capacity_leo_kg", "value": leo})
    if tli:
        facts.append({"quantity": "capacity_tli_kg", "value": tli})
    if moon_price:
        facts.append({"quantity": "price_usd_per_kg_lunar_surface", "value": moon_price})
    return {"id": rid, "name": rid, "status": status, "verified_by_flight": verified, "launch_site_ids": sites,
            "facts": facts}


def _ranked(rockets, priorities=lr.FACTORS, mass=1000.0, trajectories=("direct",), **kw):
    return lr.rank_launches(SITES, TRANSFERS, mass, rockets=rockets, trajectories=trajectories,
                            priorities=priorities, **kw)["options"]


def _leader(opts):
    return opts[0].candidate.site_id


# --- кандидати -----------------------------------------------------------------------------------------------


def test_candidates_and_exclusions():
    rockets = [rocket("a", ["eq", "cape"], leo=20000), rocket("nosite", [], leo=20000),
               rocket("nocap", ["cape"]), rocket("proj", ["cape"], leo=90000, status="design_target", verified=False)]
    systems = [{"id": "old", "name": "old", "active": False, "launch_site_ids": ["eq"],
                "facts": [{"quantity": "capacity_leo_kg", "value": 5000}]}]
    cands, excluded = lr.candidates(SITES, rockets, systems)
    assert {(c.site_id, c.vehicle_id) for c in cands} == {("eq", "a"), ("cape", "a"), ("cape", "proj")}
    reasons = {e["vehicle_id"]: e["reason"] for e in excluded}
    assert set(reasons) == {"nosite", "nocap", "old"}

    cands, excluded = lr.candidates(SITES, rockets, include_design_targets=False)
    assert "proj" not in {c.vehicle_id for c in cands}
    assert any(e["vehicle_id"] == "proj" for e in excluded)


# --- показники -----------------------------------------------------------------------------------------------


def test_equator_saves_fuel_and_has_two_windows():
    opts = _ranked([rocket("big", ["eq", "cape"], leo=50000)])
    by_site = {o.candidate.site_id: o for o in opts}
    eq, cape = by_site["eq"], by_site["cape"]
    assert eq.mass_leo_kg < cape.mass_leo_kg
    assert eq.dv_site_penalty_m_s < cape.dv_site_penalty_m_s
    assert eq.windows_per_day == 2 and cape.windows_per_day == 1  # Канаверал: нахил 28,5° = широта
    assert eq.factors["fuel"] == 1.0 and cape.factors["fuel"] == 0.0
    for o in opts:
        assert o.dv_total_m_s[0] <= o.dv_total_m_s[1]
        assert o.launch_cost_usd[0] <= o.launch_cost_usd[1]
        assert o.risk_range[0] <= o.risk_p <= o.risk_range[1]
        assert set(o.provisional_fields) == {"price_usd_per_kg", "failure_probability"}


def test_equator_can_lose_on_cost():
    # дешева послуга доставки на Місяць з Канаверал перемагає за ціною, хоча екватор кращий за паливом
    opts = _ranked([rocket("eq-rocket", ["eq"], leo=50000), rocket("cheap", ["cape"], leo=50000, moon_price=1000)],
                   priorities=("cost", "fuel"))
    by_site = {o.candidate.site_id: o for o in opts}
    assert by_site["eq"].factors["fuel"] > by_site["cape"].factors["fuel"]
    assert by_site["cape"].factors["cost"] > by_site["eq"].factors["cost"]
    assert _leader(opts) == "cape"
    assert "price_usd_per_kg" not in by_site["cape"].provisional_fields


def test_leader_changes_with_priorities():
    # мала ракета на екваторі майже заповнена (ризик вищий), велика на Канаверал — з великим запасом
    rockets = [rocket("small", ["eq"], leo=5600), rocket("large", ["cape"], leo=60000)]
    fuel_first = _ranked(rockets, priorities=("fuel", "risk"))
    risk_first = _ranked(rockets, priorities=("risk", "fuel"))
    assert _leader(fuel_first) == "eq"
    assert _leader(risk_first) == "cape"
    small = next(o for o in fuel_first if o.candidate.vehicle_id == "small")
    assert 0.85 < small.utilization <= 1.0


def test_capacity_filter():
    opts = _ranked([rocket("tiny", ["cape"], leo=1000), rocket("ok", ["cape"], leo=60000),
                    rocket("pegasus", ["air"], leo=400)])
    tiny = next(o for o in opts if o.candidate.vehicle_id == "tiny")
    assert not tiny.fits and tiny.launches > 1 and "кілька пусків" in tiny.fit_note
    assert opts[0].fits and opts[-1].fits is False
    assert all(o.fits for o in opts[: [o.fits for o in opts].index(False)])

    multi = _ranked([rocket("tiny", ["cape"], leo=1000), rocket("pegasus", ["air"], leo=400)],
                    allow_multiple_launches=True)
    by_id = {o.candidate.vehicle_id: o for o in multi}
    assert by_id["tiny"].fits
    assert not by_id["pegasus"].fits and "літака-носія" in by_id["pegasus"].fit_note


def test_tli_capacity_is_compared_with_mass_after_tli():
    opts = _ranked([rocket("tli", ["cape"], tli=2000)], mass=1000.0)
    o = opts[0]
    assert o.capacity_basis == "tli"
    # після TLI лишається лише ступінь посадки: маса < маси на НОО, але > маси на Місяці
    assert 1000.0 / 2000 < o.utilization < o.mass_leo_kg / 2000


def test_low_energy_is_slower_but_lighter():
    opts = _ranked([rocket("big", ["cape"], leo=60000)], trajectories=("direct", "low_energy"))
    by_traj = {o.trajectory: o for o in opts}
    assert by_traj["low_energy"].mass_leo_kg < by_traj["direct"].mass_leo_kg
    assert by_traj["low_energy"].factors["speed"] == 0.0 and by_traj["direct"].factors["speed"] == 1.0
    assert by_traj["low_energy"].dv_tli_m_s is None


def test_deterministic_and_validated():
    rockets = [rocket("a", ["eq", "cape"], leo=20000), rocket("b", ["cape"], leo=60000)]
    first = [(o.candidate.site_id, o.candidate.vehicle_id, o.score_pct) for o in _ranked(rockets)]
    second = [(o.candidate.site_id, o.candidate.vehicle_id, o.score_pct) for o in _ranked(rockets)]
    assert first == second
    ranks = [o.rank for o in _ranked(rockets)]
    assert ranks == list(range(1, len(ranks) + 1))
    maximin = _ranked(rockets, mode="maximin")
    assert all(o.score_pct == pytest.approx(100 * min(o.factors.values()), abs=0.01) for o in maximin)
    with pytest.raises(ValueError):
        _ranked(rockets, priorities=("fuel", "fuel"))
    with pytest.raises(ValueError):
        _ranked(rockets, mode="best")
    with pytest.raises(ValueError):
        _ranked(rockets, mass=0)


def test_pareto_only_among_feasible():
    opts = _ranked([rocket("tiny", ["cape"], leo=1000), rocket("a", ["eq"], leo=20000),
                    rocket("b", ["cape"], leo=60000)])
    assert any(o.pareto for o in opts)
    assert all(o.fits for o in opts if o.pareto)


# --- реальні каталоги й ефемериди -------------------------------------------------------------------------------


def test_real_catalogs_with_ephemeris():
    pytest.importorskip("naif_de440")
    from app.core import transfer
    from app.core.ephemeris import get_ephemeris

    load = lambda name: json.loads((ROOT / "app" / "data" / name).read_text(encoding="utf-8"))  # noqa: E731
    transfers = transfer.transfer_options(get_ephemeris(), datetime(2027, 7, 1))
    res = lr.rank_launches(load("launch_sites.json"), transfers, 2000.0, rockets=load("rockets.json"),
                           launch_systems=load("launch_systems.json"))
    opts = res["options"]
    assert opts and 0 <= res["moon_declination_deg"] <= 29
    ids = {o.candidate.vehicle_id for o in opts}
    assert {"falcon-heavy", "sls-block-1", "vulcan-vc6"} <= ids
    excluded = {e["vehicle_id"] for e in res["excluded"]}
    assert "starship" in excluded  # Starbase ще немає в каталозі стартів
    kourou = min(o.mass_leo_kg for o in opts if o.candidate.site_id == "kourou")
    cape = min(o.mass_leo_kg for o in opts if o.candidate.site_id == "cape-canaveral")
    assert kourou < cape  # ближче до екватора — менше палива


def test_catalog_economics_replace_provisional_fields_in_ranking():
    """D8 (синтетично): ціна й статистика польотів з каталогу прибирають тимчасові поля й змінюють вартість та ризик."""
    def option(**extra):
        facts = [{"quantity": q, "value": v} for q, v in extra.items()]
        row = rocket("synthetic", ["cape"], leo=20000)
        row["facts"] += facts
        cands, _ = lr.candidates(SITES, [row])
        return lr.evaluate(cands[0], DIRECT, 20.0, 2000.0)

    plain = option()
    assert set(plain.provisional_fields) == {"price_usd_per_kg", "failure_probability"}
    rich = option(price_usd_per_kg_leo_min=1000, price_usd_per_kg_leo_max=1500, flights_total=100, flights_failed=0)
    assert rich.provisional_fields == ()
    assert rich.launch_cost_usd[1] < plain.launch_cost_usd[0]  # дешевша ракета
    assert rich.risk_p < plain.risk_p  # 1/102 надійніше за тимчасові 2 %
    shaky = option(price_usd_per_kg_leo_min=1000, price_usd_per_kg_leo_max=1500, flights_total=20, flights_failed=5)
    assert shaky.risk_p > rich.risk_p
    only_stats = option(flights_total=100, flights_failed=0)
    assert only_stats.provisional_fields == ("price_usd_per_kg",)
