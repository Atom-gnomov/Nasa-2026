"""Стан системи Сонце–Земля–Місяць на момент часу (контракт SystemState, задача M1).

Положення — JPL DE440 (skyfield), орієнтація Місяця — IAU 2015 або ядра NAIF DE440 (app.core.moon_orientation),
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
from app.core.orbits import GM_EARTH, GM_MOON, GM_SUN, Orbit, osculating_orbit

ORBIT_POINTS = 720  # точок замкненого еліпса — лінія гладка за будь-якого наближення
PATH_POINTS = 241  # точок справжнього шляху за ±½ періоду


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
        "moon_orientation": _matrix(eph.moon_rotation(t.tdb)),
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


def _orbit_dict(orbit: Orbit, center: str, body: str, path_km: np.ndarray) -> dict:
    dev = orbit.deviation_km(path_km)
    return {
        "center": center,
        "body": body,
        "elements": {
            "a_km": round(orbit.a_km, 1),
            "e": round(orbit.e, 6),
            "inclination_deg": round(orbit.inclination_deg, 4),
            "period_days": round(orbit.period_days, 4),
            "periapsis_km": round(orbit.periapsis_km, 1),
            "apoapsis_km": round(orbit.apoapsis_km, 1),
        },
        "points_km": [[round(float(v), 1) for v in p] for p in orbit.points(ORBIT_POINTS)],
        "path_km": [[round(float(v), 1) for v in p] for p in path_km],
        "max_deviation_km": round(float(dev.max()), 1),
    }


def orbits(when: datetime) -> dict:
    """Оскулюючі орбіти Місяця (навколо Землі) і барицентру Земля–Місяць (навколо Сонця), ICRF, км.

    Еліпс — точний розв'язок задачі двох тіл для поточного вектора стану (DE440): замкнений і
    проходить через тіло. path_km — справжній шлях за ±½ періоду, max_deviation_km — найбільше
    відхилення справжнього шляху від еліпса (збурення, для Місяця — головно від Сонця).
    """
    eph = get_ephemeris()
    t = eph.time(when)
    emb = eph.kernel["earth barycenter"]

    m = (eph.moon - eph.earth).at(t)
    moon_orbit = osculating_orbit(m.position.km, m.velocity.km_per_s, GM_EARTH + GM_MOON)
    ts = eph.ts.tt_jd(t.tt + np.linspace(-0.5, 0.5, PATH_POINTS) * moon_orbit.period_days)
    moon_path = (eph.moon - eph.earth).at(ts).position.km.T

    s = (emb - eph.sun).at(t)
    earth_orbit = osculating_orbit(s.position.km, s.velocity.km_per_s, GM_SUN + GM_EARTH + GM_MOON)
    ts = eph.ts.tt_jd(t.tt + np.linspace(-0.5, 0.5, PATH_POINTS) * earth_orbit.period_days)
    earth_path = (emb - eph.sun).at(ts).position.km.T

    return {
        "datetime": t.utc_datetime().replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "frame": "icrf_km",
        "moon": _orbit_dict(moon_orbit, "earth", "moon", moon_path),
        "earth": _orbit_dict(earth_orbit, "sun", "earth_moon_barycenter", earth_path),
    }
