"""Запуски з Землі (docs/MATH.md, §13). Друга черга."""

from __future__ import annotations

import numpy as np

from app.core.constants import EARTH_EQUATOR_ROTATION_M_S


def rotation_boost_m_s(latitude_deg) -> np.ndarray:
    """Прибавка швидкості від обертання Землі на широті старту (старт на схід)."""
    return EARTH_EQUATOR_ROTATION_M_S * np.cos(np.radians(np.asarray(latitude_deg, dtype=float)))


def min_inclination_deg(latitude_deg: float) -> float:
    """Мінімальний нахил орбіти при прямому старті з широти latitude_deg."""
    return abs(latitude_deg)


def plane_change_dv_m_s(orbital_speed_m_s: float, delta_inclination_deg: float) -> float:
    """Δv = 2·v·sin(Δi / 2)."""
    return float(2 * orbital_speed_m_s * np.sin(np.radians(abs(delta_inclination_deg)) / 2))


TRAJECTORIES = {
    # Орієнтовні значення (docs/MATH.md, §13); уточнити перед використанням.
    "direct": {"name": "Пряма", "duration_days": (3.0, 5.0)},
    "low_energy": {"name": "Найекономніша", "duration_days": (90.0, 120.0)},
}
