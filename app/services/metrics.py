"""Збирає метрики для оверлею: Сонце, Земля, зв'язок."""

from dataclasses import asdict, dataclass
from datetime import datetime

from app.services import comms, ephemeris, horizon


@dataclass
class SiteMetrics:
    sun_elevation_deg: float
    sun_azimuth_deg: float
    sun_visible_fraction: float
    earth_elevation_deg: float
    earth_azimuth_deg: float
    earth_visible: bool
    signal_delay_s: float
    hours_to_sunset: float | None = None
    hours_to_earthset: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def site_metrics(lat: float, lon: float, when: datetime) -> SiteMetrics:
    sun = ephemeris.sun_position(lat, lon, when)
    earth = ephemeris.earth_position(lat, lon, when)
    mask = horizon.load_mask(lat, lon)
    return SiteMetrics(
        sun_elevation_deg=sun.elevation_deg,
        sun_azimuth_deg=sun.azimuth_deg,
        sun_visible_fraction=horizon.visible_fraction(
            sun.elevation_deg, sun.azimuth_deg, mask, horizon.SUN_ANGULAR_RADIUS_DEG
        ),
        earth_elevation_deg=earth.elevation_deg,
        earth_azimuth_deg=earth.azimuth_deg,
        earth_visible=horizon.visible_fraction(earth.elevation_deg, earth.azimuth_deg, mask) > 0,
        signal_delay_s=comms.signal_delay_s(earth.distance_km),
        # TODO: hours_to_sunset / hours_to_earthset через ephemeris.next_crossing
    )
