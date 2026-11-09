"""Збирає метрики для оверлею: Сонце, Земля, зв'язок (docs/MATH.md, §5–9)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

import numpy as np

from app.core import events
from app.core.ephemeris import get_ephemeris
from app.core.horizon import EARTH_ANGULAR_RADIUS_DEG, SUN_ANGULAR_RADIUS_DEG, disk_fraction
from app.services import dsn, horizon

SEARCH_DAYS = 30.0  # шукаємо схід/захід у межах ~лунної доби
SUN_STEP_HOURS = 1 / 3  # 20 хв (Сонце біля полюса рухається ~0,5°/год по азимуту)
EARTH_STEP_HOURS = 1.0


@dataclass
class SiteMetrics:
    """Відповідь /api/metrics. Контракт — contracts/openapi.yaml → SiteMetrics."""

    lat: float
    lon: float  # нормалізована до [−180, 180)
    height_m: float
    datetime: str  # ISO 8601 UTC із Z
    sun_elevation_deg: float
    sun_azimuth_deg: float
    sun_visible_fraction: float
    earth_elevation_deg: float
    earth_azimuth_deg: float
    earth_visible_fraction: float
    earth_visible: bool
    earth_distance_km: float
    signal_delay_s: float
    recommended_station: str | None
    hours_to_sunset: float | None = None
    hours_to_sunrise: float | None = None
    hours_to_earthset: float | None = None
    hours_to_earthrise: float | None = None
    # None у hours_to_* означає «події немає в межах event_search_hours» (напр., полярний день).
    event_search_hours: float = SEARCH_DAYS * 24

    def to_dict(self) -> dict:
        return asdict(self)


def _hours_until(start_jd: float, crossing: events.Crossing | None) -> float | None:
    return None if crossing is None else round((crossing.jd - start_jd) * 24.0, 2)


def site_metrics(lat: float, lon: float, when: datetime, height_m: float = 0.0) -> SiteMetrics:
    eph = get_ephemeris()
    t = eph.time(when)
    mask = horizon.load_mask(lat, lon, height_m)

    sun = eph.sun_track(t, lat, lon, height_m)
    earth = eph.earth_track(t, lat, lon, height_m)
    sun_frac = float(disk_fraction(sun.elevation_deg, mask.at(sun.azimuth_deg), SUN_ANGULAR_RADIUS_DEG))
    earth_frac = float(disk_fraction(earth.elevation_deg, mask.at(earth.azimuth_deg), EARTH_ANGULAR_RADIUS_DEG))

    # Видимість: будь-яка частина диска над маскою (для Сонця) / центр Землі над маскою.
    def sun_fn(jd):
        tr = eph.sun_track(eph.ts.tt_jd(jd), lat, lon, height_m)
        return tr.elevation_deg + SUN_ANGULAR_RADIUS_DEG - mask.at(tr.azimuth_deg)

    def earth_fn(jd):
        tr = eph.earth_track(eph.ts.tt_jd(jd), lat, lon, height_m)
        return tr.elevation_deg - mask.at(tr.azimuth_deg)

    jd0 = float(t.tt)
    sun_events = events.find_crossings(sun_fn, jd0, jd0 + SEARCH_DAYS, SUN_STEP_HOURS)
    earth_events = events.find_crossings(earth_fn, jd0, jd0 + SEARCH_DAYS, EARTH_STEP_HOURS)

    def first(evts, rising):
        return next((e for e in evts if e.rising == rising), None)

    link = dsn.best_link(dsn.station_links(eph, t, lat, lon, mask, dsn.load_stations(), height_m))
    distance = float(link.distance_km) if link else float(earth.distance_km)

    return SiteMetrics(
        lat=lat,
        lon=(lon + 180.0) % 360.0 - 180.0,
        height_m=height_m,
        datetime=t.utc_datetime().replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ"),
        sun_elevation_deg=round(float(sun.elevation_deg), 3),
        sun_azimuth_deg=round(float(sun.azimuth_deg), 2),
        sun_visible_fraction=round(sun_frac, 3),
        earth_elevation_deg=round(float(earth.elevation_deg), 3),
        earth_azimuth_deg=round(float(earth.azimuth_deg), 2),
        earth_visible_fraction=round(earth_frac, 3),
        earth_visible=bool(earth.elevation_deg > mask.at(earth.azimuth_deg)),
        earth_distance_km=round(float(earth.distance_km), 1),
        signal_delay_s=round(float(np.asarray(eph.signal_delay_s(distance))), 4),
        recommended_station=link.station.id if link else None,
        hours_to_sunset=_hours_until(jd0, first(sun_events, False)),
        hours_to_sunrise=_hours_until(jd0, first(sun_events, True)),
        hours_to_earthset=_hours_until(jd0, first(earth_events, False)),
        hours_to_earthrise=_hours_until(jd0, first(earth_events, True)),
    )
