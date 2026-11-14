"""Економіка ракет у каталогах D6/D7 (задача D8): ціна за кг на НОО діапазоном і статистика польотів.

Ціни — з контрактів NASA на запуск (первинні джерела), поділених на місткість на НОО з того ж каталогу; польоти —
пораховані з журналу запусків GCAT (J. McDowell, вторинне джерело) станом на as_of. Тест фіксує значення, щоб правка
без нового підрахунку не пройшла непомітно, і перевіряє, що ядро ранжування справді їх підхоплює.
"""

import json
from pathlib import Path

import pytest

from app.core import launch_rank
from app.core.launch_system import failure_from_flights

ROOT = Path(__file__).resolve().parents[1]


def _rows():
    rows = {}
    for name in ("rockets.json", "launch_systems.json"):
        for r in json.loads((ROOT / "app" / "data" / name).read_text(encoding="utf-8")):
            rows[r["id"]] = r
    return rows


def _value(row, quantity):
    found = [f["value"] for f in row["facts"] if f["quantity"] == quantity]
    assert len(found) <= 1, (row["id"], quantity)
    return found[0] if found else None


# id → (усього, невдалих) за GCAT станом на 2026-11-13
FLIGHTS = {
    "falcon-9": (681, 1), "falcon-heavy": (14, 0), "starship": (14, 4), "new-glenn": (3, 1),
    "vulcan-vc2": (2, 0), "vulcan-vc4": (2, 0), "sls-block-1": (2, 0),
    "pegasus-xl": (36, 3), "launcherone": (6, 2), "zenit-3sl-sea-launch": (36, 3),
    "ariane-62": (6, 0), "ariane-64": (3, 0),
}


def test_flight_statistics_as_counted_from_gcat():
    rows = _rows()
    for vid, (total, failed) in FLIGHTS.items():
        row = rows[vid]
        assert (_value(row, "flights_total"), _value(row, "flights_failed")) == (total, failed), vid
        for f in row["facts"]:
            if f["quantity"].startswith("flights_"):
                assert f["as_of"] == "2026-11-13" and f["source"]["kind"] == "secondary" and f["note"]
    # ракети, що ще не літали, статистики не мають (а не «0 з 0»)
    for vid in ("new-glenn-9x4", "vulcan-vc6", "long-march-10"):
        assert _value(rows[vid], "flights_total") is None, vid


def test_pegasus_counts_agree_with_the_independent_total():
    """Pegasus XL (+HAPS) з GCAT = 36; з ранніми Pegasus і Pegasus H — 46, як у Via Satellite (46-й запуск)."""
    row = _rows()["pegasus-xl"]
    assert _value(row, "flights_total") == 36
    assert any(f["quantity"] == "flights" and f["value"] == 46 for f in row["facts"])


def test_leo_price_ranges_follow_from_nasa_contracts():
    rows = _rows()
    for vid in ("falcon-9", "falcon-heavy"):
        row = rows[vid]
        cap = _value(row, "capacity_leo_kg")
        contracts = sorted(f["value"] for f in row["facts"] if f["quantity"] == "nasa_launch_contract_usd")
        assert len(contracts) == 3
        lo, hi = _value(row, "price_usd_per_kg_leo_min"), _value(row, "price_usd_per_kg_leo_max")
        assert lo == pytest.approx(contracts[0] / cap, abs=0.1) and hi == pytest.approx(contracts[-1] / cap, abs=0.1)
        for f in row["facts"]:
            if f["quantity"].startswith(("price_usd_per_kg_leo", "nasa_launch_contract")):
                assert f["source"]["kind"] == "primary" and f["source"]["url"].startswith("https://www.nasa.gov/")
                usd_m = f"${f['value'] / 1e6:g} million" if f["quantity"] == "nasa_launch_contract_usd" else None
                assert usd_m is None or usd_m in f["quote"], (vid, f["quote"])
    assert rows["falcon-9"]["facts"] and _value(rows["falcon-9"], "price_usd_per_kg_leo_min") == pytest.approx(3526.3)
    assert _value(rows["falcon-heavy"], "price_usd_per_kg_leo_max") == pytest.approx(5200.6)


def test_sls_has_production_cost_but_no_leo_price():
    row = _rows()["sls-block-1"]
    costs = sorted(f["value"] for f in row["facts"] if f["quantity"] == "production_cost_usd")
    assert costs == [2.2e9, 2.5e9]
    # місткості на НОО в каталозі немає — ціни за кг не вигадуємо
    assert _value(row, "price_usd_per_kg_leo_min") is None


def test_ranking_uses_catalog_economics_instead_of_provisional():
    rows = _rows()
    sites = json.loads((ROOT / "app" / "data" / "launch_sites.json").read_text(encoding="utf-8"))
    rockets = json.loads((ROOT / "app" / "data" / "rockets.json").read_text(encoding="utf-8"))
    cands, _ = launch_rank.candidates(sites, rockets)
    f9 = next(c for c in cands if c.vehicle_id == "falcon-9")
    assert f9.price_usd_per_kg_leo == (_value(rows["falcon-9"], "price_usd_per_kg_leo_min"),
                                       _value(rows["falcon-9"], "price_usd_per_kg_leo_max"))
    assert (f9.flights_total, f9.flights_failed) == FLIGHTS["falcon-9"]
    # правило Лапласа: (1 + 1) / (681 + 2) ≈ 0,29 %
    assert failure_from_flights(681, 1)[0] == pytest.approx(2 / 683)
