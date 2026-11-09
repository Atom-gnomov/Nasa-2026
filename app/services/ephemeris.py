"""Сервіс ефемерид: тонка обгортка над app.core.ephemeris для одного моменту часу."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.core.ephemeris import get_ephemeris


@dataclass(frozen=True)
class SkyPosition:
    azimuth_deg: float  # від півночі (на полюсі — від меридіана lon) за годинниковою стрілкою
    elevation_deg: float  # над математичним горизонтом
    distance_km: float


def _single(track) -> SkyPosition:
    return SkyPosition(float(track.azimuth_deg), float(track.elevation_deg), float(track.distance_km))


def sun_position(lat: float, lon: float, when: datetime, height_m: float = 0.0) -> SkyPosition:
    """Топоцентричне положення Сонця для точки на Місяці."""
    eph = get_ephemeris()
    return _single(eph.sun_track(eph.time(when), lat, lon, height_m))


def earth_position(lat: float, lon: float, when: datetime, height_m: float = 0.0) -> SkyPosition:
    """Топоцентричне положення центру Землі для точки на Місяці."""
    eph = get_ephemeris()
    return _single(eph.earth_track(eph.time(when), lat, lon, height_m))
