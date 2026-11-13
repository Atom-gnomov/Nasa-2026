"""Стан системи Сонце–Земля–Місяць на момент часу (контракт SystemState, задача M1).

Положення — JPL DE440 (skyfield), орієнтація Місяця — модель IAU 2015 (app.core.frames),
орієнтація Землі — ICRF → ITRS у skyfield (прецесія, нутація, зоряний час).
Підсонячна точка на Місяці враховує час світла Сонце → Місяць (~8,3 хв), як і метрики.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
from skyfield.api import wgs84
from skyfield.framelib import itrs

from app.core import frames
from app.core.ephemeris import get_ephemeris


def _latlon(vec_me) -> dict:
    lat, lon = frames.vector_to_latlon(vec_me)
    return {"lat": round(float(lat), 4), "lon": round(float(lon), 4)}


def _earth_subpoint(position) -> dict:
    """Точка на Землі (WGS84, геодезична широта), над якою тіло в зеніті."""
    gp = wgs84.subpoint_of(position)
    return {"lat": round(float(gp.latitude.degrees), 4),
            "lon": round((float(gp.longitude.degrees) + 180.0) % 360.0 - 180.0, 4)}


def _matrix(m) -> list[list[float]]:
    return [[round(float(v), 9) for v in row] for row in np.asarray(m)]


def system_state(when: datetime) -> dict:
    eph = get_ephemeris()
    t = eph.time(when)
    sun_km = (eph.sun - eph.earth).at(t).position.km
    moon_km = (eph.moon - eph.earth).at(t).position.km

    # Фаза Місяця: кут Сонце–Місяць–Земля (фазовий кут) і частка освітленого диска з Землі
    to_sun = eph.sun_vector_me(t)
    to_earth = eph.earth_vector_me(t)
    cos_phase = float(np.dot(to_sun, to_earth) / (np.linalg.norm(to_sun) * np.linalg.norm(to_earth)))
    phase_deg = float(np.degrees(np.arccos(np.clip(cos_phase, -1.0, 1.0))))

    return {
        "datetime": t.utc_datetime().replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "frame": "icrf_geocentric_km",
        "sun_km": [round(float(v), 1) for v in sun_km],
        "moon_km": [round(float(v), 3) for v in moon_km],
        "moon_orientation": _matrix(frames.icrf_to_moon_me(t.tdb)),
        "sub_solar_point": _latlon(to_sun),
        "sub_earth_point": _latlon(to_earth),
        "earth_rotation_deg": round(float(t.gast) * 15.0 % 360.0, 4),
        "earth_orientation": _matrix(itrs.rotation_at(t)),
        "earth_sub_solar_point": _earth_subpoint(eph.earth.at(t).observe(eph.sun).apparent()),
        "earth_sub_lunar_point": _earth_subpoint((eph.moon - eph.earth).at(t)),
        "moon_illumination": {
            "fraction": round((1.0 + cos_phase) / 2.0, 5),
            "phase_angle_deg": round(phase_deg, 4),
        },
    }
