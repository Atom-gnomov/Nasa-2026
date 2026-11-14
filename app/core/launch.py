"""Запуски з Землі: прибавка від обертання, азимут, нахил, вікна й доворот площини (docs/MATH.md, §13, §21.2–21.4).

Задача M19. Площину орбіти задаємо нормаллю в ICRF (екватор J2000); прецесію до дати не враховуємо
(похибка за 2020–2060 — до ~0,5° у прямому сходженні, тобто ~2 хв у часі вікна). Азимут — від півночі
за годинниковою стрілкою; «інерційний» — у невертовій системі, «відносно Землі» — напрямок на старті.
Чисті функції без Flask.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

from app.core.constants import EARTH_EQUATOR_ROTATION_M_S, J2000_JD

# Колова швидкість на паркувальній орбіті ≈ 185 км (MATH §21.4: «v ≈ 7,8 км/с»)
PARKING_ORBIT_SPEED_M_S = 7_793.0
SIDEREAL_DAY_S = 86_164.0905


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


# --- азимут і нахил (§21.2) ------------------------------------------------------------------------------------


def _check_lat(latitude_deg: float) -> None:
    if not -90.0 < latitude_deg < 90.0:
        raise ValueError("Широта старту має бути в межах (−90; 90)")


def inclination_from_azimuth_deg(latitude_deg: float, azimuth_deg: float) -> float:
    """Нахил орбіти при старті з широти φ під інерційним азимутом A: cos i = sin A · cos φ."""
    _check_lat(latitude_deg)
    c = math.sin(math.radians(azimuth_deg)) * math.cos(math.radians(latitude_deg))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def azimuths_for_inclination_deg(latitude_deg: float, inclination_deg: float) -> tuple[float, float] | None:
    """Два інерційні азимути (на північний схід і на південний схід) для нахилу i з широти φ.

    sin A = cos i / cos φ; None — нахил недосяжний прямим стартом (i < |φ|).
    """
    _check_lat(latitude_deg)
    s = math.cos(math.radians(inclination_deg)) / math.cos(math.radians(latitude_deg))
    if abs(s) > 1.0 + 1e-12:
        return None
    a = math.degrees(math.asin(max(-1.0, min(1.0, s))))
    return a % 360.0, (180.0 - a) % 360.0


def ground_azimuth_deg(latitude_deg: float, inertial_azimuth_deg: float,
                       orbital_speed_m_s: float = PARKING_ORBIT_SPEED_M_S) -> float:
    """Азимут відносно Землі: A_рух = atan2(v·sin A − v_оберт, v·cos A), v_оберт = 465,1·cos φ."""
    a = math.radians(inertial_azimuth_deg)
    v_rot = float(rotation_boost_m_s(latitude_deg))
    return math.degrees(math.atan2(orbital_speed_m_s * math.sin(a) - v_rot, orbital_speed_m_s * math.cos(a))) % 360.0


def rotation_gain_m_s(latitude_deg: float, inertial_azimuth_deg: float) -> float:
    """Частина обертання Землі, що йде в орбітальну швидкість: v_оберт · sin A (на захід — від'ємна)."""
    return float(rotation_boost_m_s(latitude_deg)) * math.sin(math.radians(inertial_azimuth_deg))


def _azimuth_allowed(azimuth_deg: float, limits: tuple[float, float] | None) -> bool:
    if limits is None:
        return True
    lo, hi = limits[0] % 360.0, limits[1] % 360.0
    a = azimuth_deg % 360.0
    return lo <= a <= hi if lo <= hi else (a >= lo or a <= hi)


def _nearest_allowed(azimuth_deg: float, limits: tuple[float, float]) -> float:
    """Найближча до azimuth_deg межа дозволеного сектора."""
    return min((limits[0] % 360.0, limits[1] % 360.0),
               key=lambda x: abs((x - azimuth_deg + 180.0) % 360.0 - 180.0))


# --- геометрія відльоту з майданчика (§21.2–21.4) ---------------------------------------------------------------


@dataclass(frozen=True)
class SiteDeparture:
    """Що коштує вивести апарат з майданчика в площину заданого нахилу."""

    latitude_deg: float
    target_inclination_deg: float
    launch_inclination_deg: float  # нахил, у який реально стартуємо
    windows_per_day: int  # 0 — прямого вікна немає, лише з доворотом
    inertial_azimuths_deg: tuple[float, ...]  # дозволені азимути старту (інерційні)
    ground_azimuths_deg: tuple[float, ...]
    rotation_gain_m_s: float
    rotation_loss_m_s: float  # недобір відносно старту на схід з екватора (465,1 м/с)
    plane_change_deg: float
    plane_change_dv_m_s: float
    dv_penalty_m_s: float  # rotation_loss + plane_change_dv — добавка до Δv відносно ідеального старту
    azimuth_limited: bool  # азимут обмежено безпекою запусків

    def to_dict(self) -> dict:
        return asdict(self)


def site_departure(latitude_deg: float, target_inclination_deg: float,
                   azimuth_limits_deg: tuple[float, float] | None = None,
                   orbital_speed_m_s: float = PARKING_ORBIT_SPEED_M_S) -> SiteDeparture:
    """Старт з широти φ у площину нахилу i (§21.2–21.4).

    - |φ| < i: два вікна на добу (висхідний і низхідний азимути), без довороту;
    - |φ| = i: одне вікно (старт точно на схід);
    - |φ| > i: прямого вікна немає — старт на схід (нахил |φ|) і доворот на Δi = |φ| − i.
    azimuth_limits_deg — дозволений сектор азимутів (від, до; за годинниковою стрілкою), якщо відомий з
    першоджерел (D6). Якщо потрібні азимути заборонені, стартуємо під найближчим дозволеним і довертаємо площину.
    """
    _check_lat(latitude_deg)
    if not 0.0 <= target_inclination_deg <= 180.0:
        raise ValueError("Нахил має бути в межах 0…180°")
    azimuths = azimuths_for_inclination_deg(latitude_deg, target_inclination_deg)
    if azimuths is None:  # i < |φ|: прямого вікна немає — старт на схід (нахил |φ|) і доворот
        candidates: tuple[float, ...] = (90.0,)
        direct = False
    else:
        candidates = (azimuths[0],) if abs(azimuths[0] - azimuths[1]) < 1e-9 else azimuths
        direct = True

    allowed = tuple(a for a in candidates if _azimuth_allowed(a, azimuth_limits_deg))
    limited = len(allowed) < len(candidates)
    if not allowed:  # потрібні азимути заборонені: найближчий дозволений + доворот
        allowed = (min((_nearest_allowed(a, azimuth_limits_deg) for a in candidates),
                       key=lambda x: min(abs((x - a + 180.0) % 360.0 - 180.0) for a in candidates)),)
        direct = False

    windows = len(allowed) if direct else 0
    launch_inc = target_inclination_deg if direct else inclination_from_azimuth_deg(latitude_deg, allowed[0])
    delta_i = abs(launch_inc - target_inclination_deg)
    gain = rotation_gain_m_s(latitude_deg, allowed[0])
    loss = EARTH_EQUATOR_ROTATION_M_S - gain
    dv_plane = plane_change_dv_m_s(orbital_speed_m_s, delta_i)
    return SiteDeparture(
        latitude_deg=float(latitude_deg),
        target_inclination_deg=float(target_inclination_deg),
        launch_inclination_deg=float(launch_inc),
        windows_per_day=int(windows),
        inertial_azimuths_deg=tuple(float(a) for a in allowed),
        ground_azimuths_deg=tuple(ground_azimuth_deg(latitude_deg, a, orbital_speed_m_s) for a in allowed),
        rotation_gain_m_s=float(gain),
        rotation_loss_m_s=float(loss),
        plane_change_deg=float(delta_i),
        plane_change_dv_m_s=float(dv_plane),
        dv_penalty_m_s=float(loss + dv_plane),
        azimuth_limited=bool(limited),
    )


def best_inclination_deg(latitude_deg: float, moon_declination_deg: float) -> float:
    """Найвигідніший нахил площини відльоту до Місяця з широти φ: max(|φ|, |δ_Місяця|).

    Площина має містити напрямок на Місяць (нахил ≥ |δ|) і бути досяжною з майданчика (нахил ≥ |φ|);
    менший нахил — більша частка обертання Землі (прибавка = 465,1·cos i).
    """
    return max(abs(latitude_deg), abs(moon_declination_deg))


# --- моменти вікон (§21.3) --------------------------------------------------------------------------------------


def _utc(when: datetime) -> datetime:
    return when.replace(tzinfo=timezone.utc) if when.tzinfo is None else when.astimezone(timezone.utc)


def _julian_date(when: datetime) -> float:
    return J2000_JD + (_utc(when) - datetime(2000, 1, 1, 12, tzinfo=timezone.utc)).total_seconds() / 86400.0


def gmst_deg(when: datetime) -> float:
    """Середній зоряний час Гринвіча, градуси (IAU 1982, лінійна частина; похибка < 0,1 с)."""
    return (280.46061837 + 360.98564736629 * (_julian_date(when) - J2000_JD)) % 360.0


def site_unit_vector(latitude_deg: float, longitude_deg: float, when: datetime) -> np.ndarray:
    """Напрямок на майданчик з центру Землі в ICRF (сферична Земля)."""
    lat, ra = math.radians(latitude_deg), math.radians(gmst_deg(when) + longitude_deg)
    return np.array([math.cos(lat) * math.cos(ra), math.cos(lat) * math.sin(ra), math.sin(lat)])


@dataclass(frozen=True)
class LaunchWindow:
    time_utc: datetime
    inertial_azimuth_deg: float
    direction: str  # "northeast" | "southeast" (для ретроградних — "northwest" | "southwest")


def plane_normal(inclination_deg: float, raan_deg: float) -> np.ndarray:
    """Нормаль до площини орбіти з нахилом i і довготою висхідного вузла Ω (ICRF)."""
    i, o = math.radians(inclination_deg), math.radians(raan_deg)
    return np.array([math.sin(i) * math.sin(o), -math.sin(i) * math.cos(o), math.cos(i)])


def launch_windows(latitude_deg: float, longitude_deg: float, normal, start: datetime,
                   days: float = 1.0) -> list[LaunchWindow]:
    """Моменти, коли майданчик проходить через площину з нормаллю normal (вікна прямого старту без довороту).

    Умова: n · r_майданчика(t) = 0. Розв'язок у куті α = GMST + λ: n_z·sin φ + cos φ·ρ·cos(α − α₀) = 0.
    За зоряну добу — два розв'язки, якщо |φ| < i; жодного, якщо |φ| > i.
    """
    _check_lat(latitude_deg)
    n = np.asarray(normal, dtype=float)
    n = n / np.linalg.norm(n)
    rho = math.hypot(n[0], n[1])
    lat = math.radians(latitude_deg)
    if rho < 1e-12:
        return []  # екваторіальна площина: майданчик поза екватором її не перетинає
    c = -n[2] * math.sin(lat) / (rho * math.cos(lat))
    if abs(c) > 1.0:
        return []
    alpha0 = math.atan2(n[1], n[0])
    roots = {(alpha0 + math.acos(c)) % (2 * math.pi), (alpha0 - math.acos(c)) % (2 * math.pi)}
    start = _utc(start)
    alpha_start = math.radians(gmst_deg(start) + longitude_deg)
    rate = 2 * math.pi / SIDEREAL_DAY_S
    end = start + timedelta(days=days)
    windows = []
    for root in roots:
        t = start + timedelta(seconds=((root - alpha_start) % (2 * math.pi)) / rate)
        while t < end:
            windows.append(_window_at(t, latitude_deg, longitude_deg, n))
            t += timedelta(seconds=SIDEREAL_DAY_S)
    return sorted(windows, key=lambda w: w.time_utc)


def _window_at(t: datetime, latitude_deg: float, longitude_deg: float, n: np.ndarray) -> LaunchWindow:
    r = site_unit_vector(latitude_deg, longitude_deg, t)
    d = np.cross(n, r)  # напрямок руху по орбіті (прямий рух навколо n)
    lat, ra = math.radians(latitude_deg), math.radians(gmst_deg(t) + longitude_deg)
    east = np.array([-math.sin(ra), math.cos(ra), 0.0])
    north = np.array([-math.sin(lat) * math.cos(ra), -math.sin(lat) * math.sin(ra), math.cos(lat)])
    az = math.degrees(math.atan2(d @ east, d @ north)) % 360.0
    ns = "north" if d @ north >= 0 else "south"
    ew = "east" if d @ east >= 0 else "west"
    return LaunchWindow(time_utc=t.replace(microsecond=0), inertial_azimuth_deg=az, direction=ns + ew)
