"""Часові ряди й підсумки за період для точки (контракт Timeline, задача B3; docs/MATH.md, §8–10).

Сонце, Земля й станції DSN — JPL DE440; горизонт — маска з рельєфу LOLA (app.services.horizon),
тобто тіні від гір і стінок кратерів ураховано. Енергія — вертикальна панель 1 м² зі стеженням
за Сонцем, η = 0,30 (§10).
"""

from __future__ import annotations

from datetime import datetime

import numpy as np

from app.core import power, stats
from app.core.ephemeris import get_ephemeris
from app.services import dsn, horizon, visibility

MAX_POINTS = 5000  # більше точок — сервер збільшує крок (див. контракт /timeline)
MAX_PERIOD_DAYS = 400


def timeline(lat: float, lon: float, start: datetime, end: datetime, step_h: float = 1.0,
             height_m: float = 0.0) -> dict:
    span_h = (end - start).total_seconds() / 3600.0
    if span_h <= 0:
        raise ValueError("Кінець періоду має бути пізніше за початок")
    if span_h > MAX_PERIOD_DAYS * 24:
        raise ValueError(f"Період довший за {MAX_PERIOD_DAYS} діб")
    step = max(step_h, span_h / (MAX_POINTS - 1))
    hours = np.arange(0.0, span_h + 1e-9, step)

    eph = get_ephemeris()
    t = eph.time_grid(start, hours)
    mask = horizon.load_mask(lat, lon, height_m)
    sun, earth, sun_frac, earth_frac = visibility.sun_earth_visibility(eph, t, mask, lat, lon, height_m)
    links = dsn.station_links(eph, t, lat, lon, mask, dsn.load_stations(), height_m)
    comm = np.any([lk.available for lk in links], axis=0)
    p = power.panel_power_w(sun.elevation_deg, sun_frac, sun.distance_km)

    summary = {
        "period_h": round(len(hours) * step, 3),
        "sun_hours": round(stats.total_hours(sun_frac, step), 2),
        "comm_hours": round(stats.total_hours(comm, step), 2),
        "sun_fraction": round(stats.fraction_of_time(sun_frac), 4),
        "comm_fraction": round(stats.fraction_of_time(comm), 4),
        "longest_night_h": round(stats.longest_run_hours(sun_frac <= 0.0, step), 2),
        "longest_comm_gap_h": round(stats.longest_run_hours(~comm, step), 2),
        "energy_wh_per_m2": round(float(np.sum(p) * step), 1),
        # додано зворотно сумісно: Земля над горизонтом (незалежно від станцій)
        "earth_hours": round(stats.total_hours(earth_frac > 0.5, step), 2),
        "earth_fraction": round(stats.fraction_of_time(earth_frac > 0.5), 4),
    }
    times = [x.strftime("%Y-%m-%dT%H:%M:%SZ") for x in t.utc_datetime()]
    r2 = lambda a: [round(float(v), 2) for v in np.atleast_1d(a)]  # noqa: E731
    r3 = lambda a: [round(float(v), 3) for v in np.atleast_1d(a)]  # noqa: E731
    return {
        "lat": lat,
        "lon": (lon + 180.0) % 360.0 - 180.0,
        "height_m": height_m,
        "step_h": round(step, 4),
        "times": times,
        "sun": {"azimuth_deg": r2(sun.azimuth_deg), "elevation_deg": r3(sun.elevation_deg),
                "visible_fraction": r3(sun_frac)},
        "earth": {"azimuth_deg": r2(earth.azimuth_deg), "elevation_deg": r3(earth.elevation_deg),
                  "visible_fraction": r3(earth_frac)},
        "stations": [{"station_id": lk.station.id, "available": [bool(v) for v in np.atleast_1d(lk.available)],
                      "moon_elevation_deg": r2(lk.moon_elevation_deg)} for lk in links],
        "summary": summary,
        "horizon_source": horizon.mask_source(lat, lon),
    }


def horizon_mask(lat: float, lon: float, height_m: float = 0.0) -> dict:
    """Маска горизонту точки + частка відкритого неба й оцінка дози ГКП (docs/MATH.md, §6, §12)."""
    from app.core import radiation

    mask = horizon.load_mask(lat, lon, height_m)
    return {
        "lat": lat,
        "lon": (lon + 180.0) % 360.0 - 180.0,
        "observer_height_m": height_m,
        "azimuth_step_deg": mask.step_deg,
        "elevations_deg": [round(float(v), 3) for v in mask.elevations_deg],
        "source": horizon.mask_source(lat, lon),
        "max_distance_km": horizon.MAX_DISTANCE_KM,
        "sky_view_fraction": round(mask.sky_view_fraction(), 4),
        "max_elevation_deg": round(float(np.max(mask.elevations_deg)), 3),
        "gcr_dose_usv_per_day": round(radiation.dose_rate_usv_per_day(mask), 1),
    }
