"""Сходи й заходи Сонця, Землі та доступність станцій DSN для точки за період (контракт EventList; MATH.md, §7).

Видимість — функція, що перетинає нуль: Сонце — верхній край диска над маскою горизонту; Земля — центр над
маскою; станція — запас min(станція над маскою точки, Місяць над мінімальним кутом антени).
"""

from __future__ import annotations

from datetime import datetime

import numpy as np

from app.core import events
from app.core.ephemeris import Ephemeris, get_ephemeris
from app.core.horizon import SUN_ANGULAR_RADIUS_DEG, HorizonMask
from app.services import dsn, horizon

MAX_PERIOD_DAYS = 120
SUN_STEP_H = 1 / 3  # Сонце біля полюса рухається ~0,5°/год по азимуту
EARTH_STEP_H = 1.0
STATION_STEP_H = 0.5  # вікна станцій ~ години: крок має бути меншим за найкоротше


def _iso(eph: Ephemeris, jds: list[float]) -> list[str]:
    if not jds:
        return []
    times = eph.ts.tt_jd(np.asarray(jds)).utc_datetime()
    return [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in np.atleast_1d(times)]


def point_events(lat: float, lon: float, start: datetime, end: datetime, height_m: float = 0.0) -> dict:
    span_d = (end - start).total_seconds() / 86400.0
    if span_d <= 0:
        raise ValueError("Кінець періоду має бути пізніше за початок")
    if span_d > MAX_PERIOD_DAYS:
        raise ValueError(f"Період довший за {MAX_PERIOD_DAYS} діб")

    eph = get_ephemeris()
    mask: HorizonMask = horizon.load_mask(lat, lon, height_m)
    jd0 = float(eph.time(start).tt)
    jd1 = jd0 + span_d

    def sun_fn(jd):
        tr = eph.sun_track(eph.ts.tt_jd(jd), lat, lon, height_m)
        return tr.elevation_deg + SUN_ANGULAR_RADIUS_DEG - mask.at(tr.azimuth_deg)

    def earth_fn(jd):
        tr = eph.earth_track(eph.ts.tt_jd(jd), lat, lon, height_m)
        return tr.elevation_deg - mask.at(tr.azimuth_deg)

    def station_fn(st):
        def fn(jd):
            t = eph.ts.tt_jd(jd)
            from_moon = eph.station_track(t, lat, lon, st.lat, st.lon, st.elevation_m, height_m)
            from_earth = eph.moon_from_station(t, st.lat, st.lon, st.elevation_m)
            return np.minimum(from_moon.elevation_deg - mask.at(from_moon.azimuth_deg),
                              from_earth.elevation_deg - st.min_elevation_deg)
        return fn

    sources = [("sun", sun_fn, SUN_STEP_H), ("earth", earth_fn, EARTH_STEP_H)]
    sources += [(f"station:{st.id}", station_fn(st), STATION_STEP_H) for st in dsn.load_stations()]

    out = []
    for body, fn, step in sources:
        crossings = events.find_crossings(fn, jd0, jd1, step)
        for c, iso in zip(crossings, _iso(eph, [c.jd for c in crossings]), strict=True):
            out.append({"body": body, "kind": "rise" if c.rising else "set", "datetime": iso})
    out.sort(key=lambda e: (e["datetime"], e["body"]))
    return {
        "lat": lat,
        "lon": (lon + 180.0) % 360.0 - 180.0,
        "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "events": out,
    }
