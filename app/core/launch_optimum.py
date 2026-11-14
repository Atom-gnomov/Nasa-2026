"""Оптимальна точка старту з Землі до Місяця: геометрія площини відльоту (docs/MATH.md, §21.2–21.3; П-12).

Площина перельоту має містити напрямок на Місяць у момент прибуття `u` (ICRF). Серед таких площин:
    • найменший нахил до екватора — |δ_Місяця| (дві площини: висхідний і низхідний варіанти);
    • прибавка від обертання Землі для площини з нахилом i — 465,1·cos i (для будь-якої широти |φ| ≤ i), тому
      за паливом однаково найкращі всі точки, що лежать у площині з найменшим нахилом, — це велике коло на Землі;
    • майданчик потрапляє в таку площину двічі на добу — момент вікна залежить від довготи (очікування);
      стартувати «зараз» можна в площину через майданчик і Місяць, але її нахил більший (більше пального).
Чисті функції на numpy; напрямок на Місяць як функцію моменту старту дає сервіс (ефемериди DE440).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import datetime

import numpy as np

from app.core.constants import EARTH_EQUATOR_ROTATION_M_S
from app.core.launch import gmst_deg, launch_windows, site_unit_vector


def _unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v)


def declination_deg(u) -> float:
    u = _unit(u)
    return math.degrees(math.asin(float(np.clip(u[2], -1.0, 1.0))))


def inclination_deg(normal) -> float:
    return math.degrees(math.acos(float(np.clip(_unit(normal)[2], -1.0, 1.0))))


def rotation_penalty_m_s(inclination: float) -> float:
    """Недобір прибавки від обертання Землі для площини з нахилом i відносно старту на схід з екватора."""
    return float(EARTH_EQUATOR_ROTATION_M_S * (1.0 - math.cos(math.radians(min(abs(inclination), 90.0)))))


def planes_through(u, inclination: float) -> list[np.ndarray]:
    """Нормалі (прямий рух, n_z = cos i) площин із нахилом i, що містять напрямок u. i < |δ| — жодної."""
    u = _unit(u)
    i = math.radians(inclination)
    rho = math.hypot(u[0], u[1])
    if math.sin(i) < 1e-12 or rho < 1e-12:
        return [np.array([0.0, 0.0, 1.0])] if abs(u[2]) < 1e-9 else []
    c = -u[2] / (rho * math.tan(i))
    if abs(c) > 1.0 + 1e-12:
        return []
    beta = math.atan2(u[1], u[0])
    a = math.asin(max(-1.0, min(1.0, c)))
    out = []
    for raan in (beta + a, beta + math.pi - a):
        n = np.array([math.sin(i) * math.sin(raan), -math.sin(i) * math.cos(raan), math.cos(i)])
        if not any(np.allclose(n, m, atol=1e-9) for m in out):
            out.append(n)
    return out


def plane_through_site(site_icrf, u) -> np.ndarray:
    """Нормаль площини прямого руху через майданчик (ICRF у момент старту) і напрямок на Місяць."""
    n = np.cross(_unit(site_icrf), _unit(u))
    if np.linalg.norm(n) < 1e-12:
        raise ValueError("Майданчик і Місяць на одній прямій — площина не визначена")
    n = _unit(n)
    return n if n[2] >= 0 else -n


def _to_latlon(points_icrf: np.ndarray, when: datetime) -> tuple[np.ndarray, np.ndarray]:
    lat = np.degrees(np.arcsin(np.clip(points_icrf[:, 2], -1.0, 1.0)))
    ra = np.degrees(np.arctan2(points_icrf[:, 1], points_icrf[:, 0]))
    lon = (ra - gmst_deg(when) + 180.0) % 360.0 - 180.0
    return lat, lon


def ground_track(normal, when: datetime, n: int = 181) -> tuple[np.ndarray, np.ndarray]:
    """Велике коло площини на поверхні Землі в момент `when` (широти й довготи, градуси; замкнене)."""
    nrm = _unit(normal)
    p = _unit(np.cross([0.0, 0.0, 1.0], nrm)) if math.hypot(nrm[0], nrm[1]) > 1e-12 else np.array([1.0, 0.0, 0.0])
    q = np.cross(nrm, p)
    s = np.linspace(0.0, 2 * math.pi, n)
    pts = np.cos(s)[:, None] * p + np.sin(s)[:, None] * q
    return _to_latlon(pts, when)


def ascending_node_lon(normal, when: datetime) -> float:
    """Довгота висхідного вузла площини на екваторі в момент `when` — там старт на екваторі без очікування."""
    nrm = _unit(normal)
    node = np.cross([0.0, 0.0, 1.0], nrm)
    if np.linalg.norm(node) < 1e-12:
        return 0.0
    lat, lon = _to_latlon(_unit(node)[None, :], when)
    return float(lon[0])


def earliest_window(lat: float, lon: float, moon_dir: Callable[[datetime], np.ndarray], start: datetime,
                    inclination: float, days: float = 1.5, iterations: int = 4) -> tuple[datetime, np.ndarray] | None:
    """Найближчий момент старту з точки (lat, lon) у площину з нахилом `inclination`, що містить напрямок на Місяць.

    Напрямок `moon_dir(момент_старту)` залежить від моменту старту (Місяць зміщується ≈ 13°/добу), тому момент
    уточнюється кількома ітераціями. None — вікна в межах `days` немає (наприклад, i < |φ|).
    """
    t = start
    best: tuple[datetime, np.ndarray] | None = None
    for _ in range(iterations):
        u = moon_dir(t)
        candidates = []
        for n in planes_through(u, inclination):
            for w in launch_windows(lat, lon, n, start, days=days):
                candidates.append((w.time_utc, n))
        if not candidates:
            return best
        t_new, n_new = min(candidates, key=lambda c: c[0])
        best = (t_new, n_new)
        if abs((t_new - t).total_seconds()) < 60:
            break
        t = t_new
    return best


def wait_hours(start: datetime, departure: datetime) -> float:
    return max(0.0, (departure - start).total_seconds() / 3600.0)


def site_icrf(lat: float, lon: float, when: datetime) -> np.ndarray:
    return site_unit_vector(lat, lon, when)

