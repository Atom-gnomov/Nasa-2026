"""Збирає метрики для оверлею: Сонце, Земля, зв'язок, енергія (docs/MATH.md, §5–10)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

import numpy as np

from app.core import events, frames, power
from app.core.ephemeris import get_ephemeris
from app.services import dsn, horizon, visibility

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
    # --- додано зворотно сумісно (docs/MATH.md, §9–10) ---
    local_solar_time_h: float | None = None  # 12 год — Сонце на меридіані точки
    sun_distance_km: float | None = None
    solar_irradiance_w_m2: float | None = None  # S = 1361 · (1 а.о. / r)²
    panel_power_vertical_w_m2: float | None = None  # 1 м², η = 0,30, вертикальна зі стеженням за Сонцем
    panel_power_horizontal_w_m2: float | None = None  # 1 м², η = 0,30, лежить на ґрунті
    horizon_source: str | None = None  # DEM, з якого збудовано маску горизонту, або flat
    stations: list[dict] = field(default_factory=list)  # усі станції DSN у цей момент

    def to_dict(self) -> dict:
        return asdict(self)


def _hours_until(start_jd: float, crossing: events.Crossing | None) -> float | None:
    return None if crossing is None else round((crossing.jd - start_jd) * 24.0, 2)


def site_metrics(lat: float, lon: float, when: datetime, height_m: float = 0.0) -> SiteMetrics:
    eph = get_ephemeris()
    t = eph.time(when)
    mask = horizon.load_mask(lat, lon, height_m)

    sun, earth, sun_frac, earth_frac = visibility.sun_earth_visibility(eph, t, mask, lat, lon, height_m)
    sun_frac, earth_frac = float(sun_frac), float(earth_frac)

    # Видимість: будь-яка частина диска над маскою (для Сонця) / центр Землі над маскою.
    sun_fn = visibility.sun_margin_fn(eph, mask, lat, lon, height_m)
    earth_fn = visibility.earth_margin_fn(eph, mask, lat, lon, height_m)

    jd0 = float(t.tt)
    sun_events = events.find_crossings(sun_fn, jd0, jd0 + SEARCH_DAYS, SUN_STEP_HOURS)
    earth_events = events.find_crossings(earth_fn, jd0, jd0 + SEARCH_DAYS, EARTH_STEP_HOURS)

    def first(evts, rising):
        return next((e for e in evts if e.rising == rising), None)

    links = dsn.station_links(eph, t, lat, lon, mask, dsn.load_stations(), height_m)
    link = dsn.best_link(links)
    distance = float(link.distance_km) if link else float(earth.distance_km)

    _, sub_lon = frames.vector_to_latlon(eph.sun_vector_me(t))
    sun_km = float(sun.distance_km)
    stations = [{
        "id": lk.station.id,
        "name": lk.station.name,
        "moon_elevation_deg": round(float(lk.moon_elevation_deg), 2),  # Місяць над горизонтом станції
        "station_elevation_deg": round(float(lk.station_elevation_deg), 3),  # станція над горизонтом точки
        "min_elevation_deg": lk.station.min_elevation_deg,
        "available": bool(np.all(lk.available)),
    } for lk in links]

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
        local_solar_time_h=round(float((12.0 + (((lon - float(sub_lon)) + 180.0) % 360.0 - 180.0) / 15.0) % 24.0), 3),
        sun_distance_km=round(sun_km, 0),
        solar_irradiance_w_m2=round(float(power.solar_irradiance(sun_km)), 1),
        panel_power_vertical_w_m2=round(float(power.panel_power_w(sun.elevation_deg, sun_frac, sun_km)), 1),
        panel_power_horizontal_w_m2=round(float(power.panel_power_w(sun.elevation_deg, sun_frac, sun_km,
                                                                     mode="horizontal")), 1),
        horizon_source=horizon.mask_source(lat, lon),
        stations=stations,
    )
