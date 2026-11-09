"""Рівноважна температура поверхні без теплової інерції (docs/MATH.md, §11). Друга черга."""

from __future__ import annotations

import numpy as np

from app.core.constants import SOLAR_CONSTANT_W_M2, STEFAN_BOLTZMANN


def equilibrium_temperature_k(cos_incidence, albedo: float = 0.12, emissivity: float = 0.95,
                              irradiance_w_m2: float = SOLAR_CONSTANT_W_M2) -> np.ndarray:
    """T = ((1 − A)·S·cos i / (ε·σ))^(1/4). Для cos i ≤ 0 повертає 0 — нічну температуру брати з Diviner."""
    absorbed = (1 - albedo) * irradiance_w_m2 * np.clip(np.asarray(cos_incidence, dtype=float), 0.0, None)
    return (absorbed / (emissivity * STEFAN_BOLTZMANN)) ** 0.25
