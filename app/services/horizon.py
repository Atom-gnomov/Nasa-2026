"""Радіогоризонт: перевірка видимості Сонця/Землі з урахуванням рельєфу.

Маска горизонту — кут піднесення рельєфу (градуси) для кожного азимута 0..359.
Атмосфери немає, тому рефракцію не враховуємо.
"""

from collections.abc import Sequence

SUN_ANGULAR_RADIUS_DEG = 0.267  # ~0,53° / 2


def mask_elevation(mask: Sequence[float], azimuth_deg: float) -> float:
    """Висота горизонту на заданому азимуті (лінійна інтерполяція між градусами)."""
    n = len(mask)
    if n == 0:
        return 0.0
    pos = (azimuth_deg % 360.0) * n / 360.0
    i = int(pos) % n
    frac = pos - int(pos)
    return mask[i] * (1 - frac) + mask[(i + 1) % n] * frac


def visible_fraction(
    elevation_deg: float,
    azimuth_deg: float,
    mask: Sequence[float] | None = None,
    angular_radius_deg: float = 0.0,
) -> float:
    """Частка диска над горизонтом: 0 — не видно, 1 — повністю видно.

    Для точкового об'єкта (angular_radius_deg=0) повертає 0 або 1.
    Для Сонця передавайте SUN_ANGULAR_RADIUS_DEG — наближено, лінійно за висотою.
    """
    horizon = mask_elevation(mask, azimuth_deg) if mask else 0.0
    delta = elevation_deg - horizon
    if angular_radius_deg <= 0:
        return 1.0 if delta > 0 else 0.0
    if delta >= angular_radius_deg:
        return 1.0
    if delta <= -angular_radius_deg:
        return 0.0
    return (delta + angular_radius_deg) / (2 * angular_radius_deg)


def load_mask(lat: float, lon: float) -> list[float] | None:
    """Маска горизонту для точки з передрозрахованих даних (tools/).

    TODO: читати маски, згенеровані з DEM LOLA. Поки — None (гладка сфера).
    """
    return None
