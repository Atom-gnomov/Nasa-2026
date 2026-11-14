"""Дані станцій DSN і місць старту звірено з першоджерелами (задача D2).

DSN — DSN Telecommunications Link Design Handbook 810-005, модуль 301 «Coverage and Geometry», Rev. P:
  • табл. 5 «Geodetic Coordinates for DSN Stations With Respect to the WGS 84 Ellipsoid» (с. 16) — широта,
    довгота на схід і висота над еліпсоїдом у градусах/мінутах/секундах; для південної півкулі всі знаки «−»;
  • §2.2.4 (с. 24): «the absolute lower elevation limit for uplink transmission is 10.1 degrees» — нижня межа
    передавання (приймання — механічна межа ≈ 6°, але для двобічного зв'язку обмежує передавач).
https://deepspace.jpl.nasa.gov/dsndocs/810-005/301/301P.pdf
"""

import json
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[1] / "app" / "data"


def _dms(deg: float, minutes: float, seconds: float, south: bool = False) -> float:
    value = deg + minutes / 60 + seconds / 3600
    return -value if south else value


def _east_to_signed(lon_east: float) -> float:
    return lon_east - 360 if lon_east > 180 else lon_east


# Дослівно з табл. 5 модуля 301P: (широта), (довгота на схід), висота, м.
TABLE_5 = {
    "DSS-14": ((35, 25, 33.24312, False), (243, 6, 37.66244), 1001.390),
    "DSS-43": ((35, 24, 8.72724, True), (148, 58, 52.56231), 688.867),
    "DSS-63": ((40, 25, 52.35510, False), (355, 45, 7.16924), 864.816),
}


def _stations() -> dict:
    return {s["antenna"]: s for s in json.loads((DATA / "dsn_stations.json").read_text(encoding="utf-8"))}


@pytest.mark.parametrize("antenna", sorted(TABLE_5))
def test_dsn_coordinates_match_810_005_table_5(antenna):
    (lat, lon_east, height) = TABLE_5[antenna]
    station = _stations()[antenna]
    assert station["lat"] == pytest.approx(_dms(*lat), abs=1e-6)  # 1e-6° ≈ 0,1 м
    assert station["lon"] == pytest.approx(_east_to_signed(_dms(*lon_east)), abs=1e-6)
    assert station["elevation_m"] == pytest.approx(height, abs=1e-3)


def test_dsn_min_elevation_is_uplink_limit_from_810_005():
    for station in _stations().values():
        assert station["min_elevation_deg"] == 10.1


def test_launch_sites_are_marked_honestly():
    """Жодне місце старту не позначене звіреним без джерела: у кожного є примітка про джерело або його відсутність."""
    sites = {s["id"]: s for s in json.loads((DATA / "launch_sites.json").read_text(encoding="utf-8"))}
    for site in sites.values():
        assert site.get("note"), site["id"]
        if site.get("verified"):
            pytest.fail(f"{site['id']}: verified=true потребує першоджерела з точними координатами")
    # Ariane 6 User's Manual, Issue 2 Rev. 0, §6.2.3.2: «5°26’46’’ North (TBC), 52°79’22’’ West (TBC)» —
    # десяткові градуси, записані знаками ° ’ ’’ (79 хвилин неможливі).
    assert sites["kourou"]["lat"] == pytest.approx(5.2646)
    assert sites["kourou"]["lon"] == pytest.approx(-52.7922)
