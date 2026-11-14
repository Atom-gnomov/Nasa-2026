"""Спільні функції видимості Сонця, Землі й станцій DSN з точки на Місяці (задача B1).

Раніше `events`, `metrics` і `timeline` мали власні копії одних і тих самих виразів. Тут вони в одному місці,
тож виправлення маски горизонту чи кутового розміру диска не розходяться між ендпоінтами.

Видимість Сонця — будь-яка частина диска над маскою (запас кута додає радіус Сонця); Землі — центр над маскою;
станція DSN — одночасно: станція над маскою точки **і** Місяць вище мінімального кута антени (MATH §9.2).
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from app.core.horizon import EARTH_ANGULAR_RADIUS_DEG, SUN_ANGULAR_RADIUS_DEG, HorizonMask, disk_fraction

MarginFn = Callable[[float], np.ndarray]


def sun_margin_fn(eph, mask: HorizonMask, lat: float, lon: float,
                  height_m: float = 0.0) -> MarginFn:
    """jd (TT) → запас кута Сонця над маскою, градуси; перехід через 0 — схід/захід краю диска."""

    def fn(jd):
        tr = eph.sun_track(eph.ts.tt_jd(jd), lat, lon, height_m)
        return tr.elevation_deg + SUN_ANGULAR_RADIUS_DEG - mask.at(tr.azimuth_deg)

    return fn


def earth_margin_fn(eph, mask: HorizonMask, lat: float, lon: float,
                    height_m: float = 0.0) -> MarginFn:
    """jd (TT) → запас кута центра Землі над маскою, градуси."""

    def fn(jd):
        tr = eph.earth_track(eph.ts.tt_jd(jd), lat, lon, height_m)
        return tr.elevation_deg - mask.at(tr.azimuth_deg)

    return fn


def station_margin_fn(eph, mask: HorizonMask, lat: float, lon: float, station,
                      height_m: float = 0.0) -> MarginFn:
    """jd (TT) → найменший із двох запасів: станція над маскою точки й Місяць над мінімальним кутом антени."""

    def fn(jd):
        t = eph.ts.tt_jd(jd)
        from_moon = eph.station_track(t, lat, lon, station.lat, station.lon, station.elevation_m, height_m)
        from_earth = eph.moon_from_station(t, station.lat, station.lon, station.elevation_m)
        return np.minimum(from_moon.elevation_deg - mask.at(from_moon.azimuth_deg),
                          from_earth.elevation_deg - station.min_elevation_deg)

    return fn


def sun_earth_visibility(eph, t, mask: HorizonMask, lat: float, lon: float, height_m: float = 0.0):
    """Треки Сонця й Землі та частки їхніх дисків над маскою для моментів `t` (скаляр або масив).

    Повертає `(sun, earth, sun_fraction, earth_fraction)`.
    """
    sun = eph.sun_track(t, lat, lon, height_m)
    earth = eph.earth_track(t, lat, lon, height_m)
    sun_fraction = disk_fraction(sun.elevation_deg, mask.at(sun.azimuth_deg), SUN_ANGULAR_RADIUS_DEG)
    earth_fraction = disk_fraction(earth.elevation_deg, mask.at(earth.azimuth_deg), EARTH_ANGULAR_RADIUS_DEG)
    return sun, earth, sun_fraction, earth_fraction
