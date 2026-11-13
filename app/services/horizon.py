"""Сервіс радіогоризонту: маска для точки та перевірка видимості.

Математика — app.core.horizon і docs/MATH.md, §6. Рельєф — офіційні DEM LOLA (app.services.elevation):
маска рахується на льоту з найдетальнішого продукту в кожній точці променя (20 м / 80 м біля
південного полюса, далі — глобальний LDEM). Без завантажених DEM — гладка сфера, як раніше.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.dem import mosaic_height_fn
from app.core.horizon import (  # noqa: F401  (реекспорт для зручності)
    EARTH_ANGULAR_RADIUS_DEG,
    SUN_ANGULAR_RADIUS_DEG,
    HorizonMask,
    compute_mask,
    dip_deg,
    disk_fraction,
)
from app.services import elevation

MAX_DISTANCE_KM = 200.0  # далі кривина Місяця ховає навіть найвищі гори біля полюса


@lru_cache(maxsize=256)
def _terrain_mask(dems: tuple, lat: float, lon: float, observer_height_m: float) -> HorizonMask:
    return compute_mask(mosaic_height_fn(list(dems)), lat, lon, observer_height_m,
                        azimuth_step_deg=1.0, max_distance_km=MAX_DISTANCE_KM)


def mask_source(lat: float, lon: float) -> str:
    """Ідентифікатор DEM, з якого береться рельєф у точці, або 'smooth_sphere'."""
    for dem in elevation.available():
        if dem.covers(lat, lon):
            return dem.id
    return "smooth_sphere"


def load_mask(lat: float, lon: float, observer_height_m: float = 0.0) -> HorizonMask:
    """Маска горизонту для точки: з рельєфу LOLA, якщо DEM завантажено; інакше — гладка сфера."""
    dems = elevation.available()
    if not dems:
        return HorizonMask.flat(360, -dip_deg(observer_height_m))
    return _terrain_mask(dems, round(lat, 5), round(lon, 5), round(observer_height_m, 2))


def visible_fraction(elevation_deg: float, azimuth_deg: float, mask: HorizonMask | None = None,
                     angular_radius_deg: float = 0.0) -> float:
    """Частка диска над горизонтом: 0 — не видно, 1 — повністю видно."""
    horizon = float(mask.at(azimuth_deg)) if mask is not None else 0.0
    return float(disk_fraction(elevation_deg, horizon, angular_radius_deg))
