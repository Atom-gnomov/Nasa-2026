"""Сервіс радіогоризонту: маска для точки та перевірка видимості.

Математика — app.core.horizon і docs/MATH.md, §6.
"""

from __future__ import annotations

from app.core.horizon import (  # noqa: F401  (реекспорт для зручності)
    EARTH_ANGULAR_RADIUS_DEG,
    SUN_ANGULAR_RADIUS_DEG,
    HorizonMask,
    dip_deg,
    disk_fraction,
)


def load_mask(lat: float, lon: float, observer_height_m: float = 0.0) -> HorizonMask:
    """Маска горизонту для точки.

    TODO (М6): читати маски, передраховані з DEM LOLA (tools/build_horizon_masks.py).
    Поки — гладка сфера з урахуванням пониження горизонту для висоти щогли.
    """
    return HorizonMask.flat(360, -dip_deg(observer_height_m))


def visible_fraction(elevation_deg: float, azimuth_deg: float, mask: HorizonMask | None = None,
                     angular_radius_deg: float = 0.0) -> float:
    """Частка диска над горизонтом: 0 — не видно, 1 — повністю видно."""
    horizon = float(mask.at(azimuth_deg)) if mask is not None else 0.0
    return float(disk_fraction(elevation_deg, horizon, angular_radius_deg))
