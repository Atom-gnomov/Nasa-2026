"""Станції Deep Space Network та вибір станції для зв'язку (docs/MATH.md, §9)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from functools import lru_cache

import numpy as np
from flask import current_app

from app.core.ephemeris import Ephemeris
from app.core.horizon import HorizonMask


@dataclass(frozen=True)
class Station:
    id: str
    name: str
    antenna: str
    lat: float
    lon: float  # градуси на схід
    elevation_m: float
    min_elevation_deg: float = 10.0  # запасне; у dsn_stations.json — 10,1° (810-005, §2.2.4, D2)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class StationLink:
    """Стан лінії «точка на Місяці ↔ станція» у моменти часу (масиви або скаляри)."""

    station: Station
    moon_elevation_deg: np.ndarray  # Місяць над горизонтом станції
    station_elevation_deg: np.ndarray  # станція над математичним горизонтом точки на Місяці
    distance_km: np.ndarray
    available: np.ndarray  # обидві умови виконано


@lru_cache(maxsize=1)
def _load(path: str) -> tuple[Station, ...]:
    with open(path, encoding="utf-8") as f:
        return tuple(Station(**item) for item in json.load(f))


def load_stations() -> tuple[Station, ...]:
    return _load(str(current_app.config["DATA_DIR"] / "dsn_stations.json"))


def station_links(eph: Ephemeris, t, lat: float, lon: float, mask: HorizonMask,
                  stations: tuple[Station, ...], height_m: float = 0.0) -> list[StationLink]:
    """Для кожної станції: чи є прямий зв'язок з точкою на Місяці в моменти t.

    Умови: (1) станція видна з точки на Місяці над маскою рельєфу;
           (2) Місяць вище мінімального кута місця антени станції.
    """
    links = []
    for st in stations:
        from_moon = eph.station_track(t, lat, lon, st.lat, st.lon, st.elevation_m, height_m)
        from_earth = eph.moon_from_station(t, st.lat, st.lon, st.elevation_m)
        ok = (from_moon.elevation_deg > mask.at(from_moon.azimuth_deg)) & (
            from_earth.elevation_deg >= st.min_elevation_deg)
        links.append(StationLink(st, from_earth.elevation_deg, from_moon.elevation_deg,
                                 from_moon.distance_km, ok))
    return links


def best_link(links: list[StationLink]) -> StationLink | None:
    """Для одного моменту: доступна станція з найвищим Місяцем над горизонтом."""
    available = [lk for lk in links if bool(np.all(lk.available))]
    if not available:
        return None
    return max(available, key=lambda lk: float(np.max(lk.moon_elevation_deg)))
