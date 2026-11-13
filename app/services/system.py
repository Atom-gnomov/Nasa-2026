"""Стан системи Сонце–Земля–Місяць на момент часу (контракт SystemState, задача M1).

Положення — JPL DE440 (skyfield), орієнтація Місяця — модель IAU 2015 (app.core.frames).
Підсонячна точка враховує час світла Сонце → Місяць (~8,3 хв), як і метрики.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np

from app.core import frames
from app.core.ephemeris import get_ephemeris


def _latlon(vec_me) -> dict:
    lat, lon = frames.vector_to_latlon(vec_me)
    return {"lat": round(float(lat), 4), "lon": round(float(lon), 4)}


def system_state(when: datetime) -> dict:
    eph = get_ephemeris()
    t = eph.time(when)
    sun_km = (eph.sun - eph.earth).at(t).position.km
    moon_km = (eph.moon - eph.earth).at(t).position.km
    orientation = np.asarray(frames.icrf_to_moon_me(t.tdb))
    return {
        "datetime": t.utc_datetime().replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "frame": "icrf_geocentric_km",
        "sun_km": [round(float(v), 1) for v in sun_km],
        "moon_km": [round(float(v), 3) for v in moon_km],
        "moon_orientation": [[round(float(v), 9) for v in row] for row in orientation],
        "sub_solar_point": _latlon(eph.sun_vector_me(t)),
        "sub_earth_point": _latlon(eph.earth_vector_me(t)),
        "earth_rotation_deg": round(float(t.gast) * 15.0 % 360.0, 4),
    }
