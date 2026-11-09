"""Ефемериди: положення Сонця й Землі на небі точки на Місяці.

Пропозиція реалізації — skyfield + DE440/DE421 + PCK орієнтації Місяця
(див. docs/RESOURCES.md, розділ 4, і docs/MODULES.md).
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SkyPosition:
    azimuth_deg: float  # від півночі за годинниковою стрілкою
    elevation_deg: float  # над математичним горизонтом
    distance_km: float


def sun_position(lat: float, lon: float, when: datetime) -> SkyPosition:
    """Топоцентричне положення Сонця для точки на Місяці."""
    raise NotImplementedError("Ефемериди ще не підключено (app/services/ephemeris.py)")


def earth_position(lat: float, lon: float, when: datetime) -> SkyPosition:
    """Топоцентричне положення Землі для точки на Місяці."""
    raise NotImplementedError("Ефемериди ще не підключено (app/services/ephemeris.py)")


def next_crossing(lat: float, lon: float, when: datetime, body: str, rising: bool) -> datetime | None:
    """Наступний схід (rising=True) або захід тіла `body` ('sun' | 'earth') з урахуванням маски горизонту."""
    raise NotImplementedError("Пошук сходу/заходу ще не реалізовано")
