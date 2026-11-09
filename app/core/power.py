"""Енергія сонячних панелей (docs/MATH.md, §10)."""

from __future__ import annotations

import numpy as np

from app.core.constants import AU_KM, SOLAR_CONSTANT_W_M2


def solar_irradiance(sun_distance_km) -> np.ndarray:
    """Потік Сонця, Вт/м², на відстані sun_distance_km."""
    return SOLAR_CONSTANT_W_M2 * (AU_KM / np.asarray(sun_distance_km, dtype=float)) ** 2


def incidence_cosine(sun_elevation_deg, mode: str = "vertical_tracking") -> np.ndarray:
    """cos кута між нормаллю панелі й Сонцем.

    vertical_tracking — вертикальна панель, що повертається за азимутом Сонця (типово для полюса);
    horizontal        — панель лежить на ґрунті.
    """
    el = np.radians(np.asarray(sun_elevation_deg, dtype=float))
    if mode == "vertical_tracking":
        cos_i = np.cos(el)
    elif mode == "horizontal":
        cos_i = np.sin(el)
    else:
        raise ValueError(f"Невідомий режим панелі: {mode}")
    return np.clip(cos_i, 0.0, None)


def panel_power_w(sun_elevation_deg, visible_fraction, sun_distance_km,
                  area_m2: float = 1.0, efficiency: float = 0.30,
                  mode: str = "vertical_tracking") -> np.ndarray:
    """P = η · A · S · cos θ · f."""
    return (efficiency * area_m2 * solar_irradiance(sun_distance_km)
            * incidence_cosine(sun_elevation_deg, mode) * np.asarray(visible_fraction, dtype=float))
