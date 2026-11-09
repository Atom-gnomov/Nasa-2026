"""Горизонт (docs/MATH.md, §6): пониження, маска рельєфу, частка диска над горизонтом.

Атмосфери немає — рефракцію не враховуємо.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from app.core import frames
from app.core.constants import R_MOON_KM

SUN_ANGULAR_RADIUS_DEG = 0.267
EARTH_ANGULAR_RADIUS_DEG = 0.95


def dip_deg(height_m: float, radius_km: float = R_MOON_KM) -> float:
    """Пониження геометричного горизонту для спостерігача на висоті height_m над гладкою сферою."""
    h = max(height_m, 0.0) / 1000.0
    return float(np.degrees(np.arccos(radius_km / (radius_km + h))))


def horizon_distance_km(height_m: float, radius_km: float = R_MOON_KM) -> float:
    return float(np.sqrt(2 * radius_km * max(height_m, 0.0) / 1000.0))


def disk_fraction(elevation_deg, horizon_deg, radius_deg):
    """Частка площі диска над прямою лінією горизонту (сегмент круга).

    k = (el − горизонт) / r ∈ [−1, 1];  f = 1 − (acos k − k·√(1 − k²)) / π.
    Для точкового об'єкта (radius_deg = 0) — 0 або 1.
    """
    delta = np.asarray(elevation_deg, dtype=float) - np.asarray(horizon_deg, dtype=float)
    if radius_deg <= 0:
        return (delta > 0).astype(float)
    k = np.clip(delta / radius_deg, -1.0, 1.0)
    return 1.0 - (np.arccos(k) - k * np.sqrt(1.0 - k * k)) / np.pi


@dataclass(frozen=True)
class HorizonMask:
    """Кут піднесення рельєфу (градуси) на рівномірній сітці азимутів 0…360."""

    elevations_deg: np.ndarray

    @classmethod
    def flat(cls, n: int = 360, value_deg: float = 0.0) -> "HorizonMask":
        return cls(np.full(n, float(value_deg)))

    @property
    def step_deg(self) -> float:
        return 360.0 / len(self.elevations_deg)

    @property
    def azimuths_deg(self) -> np.ndarray:
        return np.arange(len(self.elevations_deg)) * self.step_deg

    def at(self, azimuth_deg):
        """Лінійна інтерполяція по азимуту з переходом через 360°."""
        m = self.elevations_deg
        pos = (np.asarray(azimuth_deg, dtype=float) % 360.0) / self.step_deg
        i = np.floor(pos).astype(int) % len(m)
        frac = pos - np.floor(pos)
        return m[i] * (1 - frac) + m[(i + 1) % len(m)] * frac

    def sky_view_fraction(self) -> float:
        """Частка відкритого неба відносно півсфери: Ω / 2π = середнє (1 − sin mask)."""
        return float(np.mean(1.0 - np.sin(np.radians(np.clip(self.elevations_deg, -90, 90)))))


# height_fn(lat, lon) → висота рельєфу відносно опорної сфери, метри (масиви однакової форми)
HeightFn = Callable[[np.ndarray, np.ndarray], np.ndarray]


def compute_mask(
    height_fn: HeightFn,
    lat: float,
    lon: float,
    observer_height_m: float = 0.0,
    azimuth_step_deg: float = 1.0,
    max_distance_km: float = 200.0,
    min_step_km: float = 0.02,
    step_growth: float = 1.01,
    radius_km: float = R_MOON_KM,
) -> HorizonMask:
    """Маска горизонту: для кожного азимута максимум кута піднесення рельєфу вздовж променя.

    Точки променя будуються по великому колу через вектори (працює й на полюсі):
        Q = cos δ · P + sin δ · (cos az · N + sin az · E),  δ = d / R.
    Кут піднесення рахується точно у векторах, без наближення малих кутів.
    Крок по відстані росте геометрично (дрібний поблизу, грубий далеко).
    """
    basis = frames.enu_basis(lat, lon)
    east, north, up = basis
    observer = frames.site_vector(lat, lon, float(height_fn(np.array(lat), np.array(lon))) + observer_height_m,
                                  radius_km)

    distances = [min_step_km]
    while distances[-1] < max_distance_km:
        distances.append(min(distances[-1] * step_growth + min_step_km, max_distance_km))
    delta = np.asarray(distances) / radius_km  # кутові відстані, радіани

    az = np.radians(np.arange(0.0, 360.0, azimuth_step_deg))
    tangent = np.cos(az)[:, None] * north + np.sin(az)[:, None] * east          # (A, 3)
    dirs = (np.cos(delta)[None, :, None] * up[None, None, :]
            + np.sin(delta)[None, :, None] * tangent[:, None, :])                 # (A, D, 3)
    t_lat, t_lon = frames.vector_to_latlon(dirs)
    t_h = np.asarray(height_fn(t_lat, t_lon), dtype=float)
    points = dirs * (radius_km + t_h / 1000.0)[..., None]
    rel = points - observer
    sin_el = (rel @ up) / np.linalg.norm(rel, axis=-1)
    return HorizonMask(np.degrees(np.arcsin(np.clip(sin_el.max(axis=1), -1, 1))))
