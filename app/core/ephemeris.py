"""Ефемериди: положення Сонця, Землі та станцій DSN відносно Місяця (docs/MATH.md, §1–2, §9).

Використовує JPL DE440 через skyfield. Ядро береться (за пріоритетом):
    1) шлях, переданий у конструктор;
    2) змінна середовища LSE_EPHEMERIS_PATH;
    3) пакет `naif-de440` з PyPI.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache

import numpy as np
from skyfield.api import load, wgs84
from skyfield.timelib import Time

from app.core import frames
from app.core.constants import C_KM_S


@dataclass(frozen=True)
class SkyTrack:
    """Траєкторія тіла на небі точки: масиви однакової довжини (або скаляри)."""

    azimuth_deg: np.ndarray
    elevation_deg: np.ndarray
    distance_km: np.ndarray


def _default_kernel_path() -> str:
    env = os.environ.get("LSE_EPHEMERIS_PATH")
    if env:
        return env
    try:
        from naif_de440 import de440
    except ImportError as exc:  # pragma: no cover - залежить від середовища
        raise RuntimeError(
            "Не знайдено ефемериди DE440: встановіть пакет naif-de440 або задайте LSE_EPHEMERIS_PATH"
        ) from exc
    return str(de440)


class Ephemeris:
    def __init__(self, kernel_path: str | None = None):
        self.ts = load.timescale(builtin=True)
        self.kernel = load(kernel_path or _default_kernel_path())
        self.sun = self.kernel["sun"]
        self.earth = self.kernel["earth"]
        self.moon = self.kernel["moon"]

    # --- час -----------------------------------------------------------------
    def time(self, when: datetime) -> Time:
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return self.ts.from_datetime(when)

    def time_grid(self, start: datetime, hours) -> Time:
        """Моменти start + hours (масив годин)."""
        t0 = self.time(start)
        return self.ts.tt_jd(t0.tt + np.asarray(hours, dtype=float) / 24.0)

    def time_range(self, start: datetime, end: datetime, step_hours: float) -> Time:
        span_h = (end - start).total_seconds() / 3600.0
        return self.time_grid(start, np.arange(0.0, span_h + 1e-9, step_hours))

    # --- вектори в системі Місяця ME, км, від центру Місяця --------------------
    def _to_me(self, t: Time, icrf_km: np.ndarray) -> np.ndarray:
        """icrf_km форми (3, N) або (3,) → (N, 3) або (3,)."""
        return frames.rotate(frames.icrf_to_moon_me(t.tdb), np.moveaxis(icrf_km, 0, -1))

    def sun_vector_me(self, t: Time) -> np.ndarray:
        """Напрямок на Сонце з поправкою на час світла (~8,3 хв)."""
        return self._to_me(t, self.moon.at(t).observe(self.sun).position.km)

    def earth_vector_me(self, t: Time) -> np.ndarray:
        """Центр Землі (час світла 1,3 с — нехтуємо)."""
        return self._to_me(t, self.earth.at(t).position.km - self.moon.at(t).position.km)

    def station_vector_me(self, t: Time, lat: float, lon: float, height_m: float = 0.0) -> np.ndarray:
        """Станція на Землі (WGS84) відносно центру Місяця."""
        station = self.earth + wgs84.latlon(lat, lon, height_m)
        return self._to_me(t, station.at(t).position.km - self.moon.at(t).position.km)

    # --- небо точки на Місяці -----------------------------------------------
    def _track(self, target_me: np.ndarray, lat: float, lon: float, height_m: float) -> SkyTrack:
        rel = target_me - frames.site_vector(lat, lon, height_m)  # топоцентрично (паралакс Землі до 0,26°)
        az, el = frames.azel(rel, frames.enu_basis(lat, lon))
        return SkyTrack(az, el, np.linalg.norm(rel, axis=-1))

    def sun_track(self, t: Time, lat: float, lon: float, height_m: float = 0.0) -> SkyTrack:
        return self._track(self.sun_vector_me(t), lat, lon, height_m)

    def earth_track(self, t: Time, lat: float, lon: float, height_m: float = 0.0) -> SkyTrack:
        return self._track(self.earth_vector_me(t), lat, lon, height_m)

    def station_track(self, t: Time, lat: float, lon: float, station_lat: float, station_lon: float,
                      station_height_m: float = 0.0, height_m: float = 0.0) -> SkyTrack:
        """Де на небі точки на Місяці знаходиться станція DSN."""
        return self._track(self.station_vector_me(t, station_lat, station_lon, station_height_m), lat, lon, height_m)

    # --- небо станції на Землі ----------------------------------------------
    def moon_from_station(self, t: Time, station_lat: float, station_lon: float,
                          station_height_m: float = 0.0) -> SkyTrack:
        """Кут місця й азимут Місяця над горизонтом станції на Землі."""
        station = self.earth + wgs84.latlon(station_lat, station_lon, station_height_m)
        alt, az, dist = station.at(t).observe(self.moon).apparent().altaz()
        return SkyTrack(az.degrees, alt.degrees, dist.km)

    @staticmethod
    def signal_delay_s(distance_km) -> np.ndarray:
        return np.asarray(distance_km) / C_KM_S


@lru_cache(maxsize=1)
def get_ephemeris() -> Ephemeris:
    """Спільний екземпляр (ядро DE440 відкривається один раз)."""
    return Ephemeris()
