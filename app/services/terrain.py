"""Ділянка рельєфу навколо точки: сітка висот з DEM LOLA для 3D-виду «з поверхні» (GET /api/terrain).

Сітка — у місцевих осях точки (схід, північ; на полюсі «північ» — напрямок на меридіан lon, docs/MATH.md, §5).
Вузол (e, n) — точка дотичної площини, спроєктована на сферу 1737,4 км по радіусу; висота береться з
найдетальнішого DEM у цьому місці (20 м / 80 м біля південного полюса, далі — глобальний LDEM). Висоти
повертаються відносно висоти самої точки; кривину Місяця рахує клієнт. Без DEM — гладка сфера.
"""

from __future__ import annotations

import base64
from functools import lru_cache

import numpy as np

from app.core import frames
from app.services import elevation

R_MOON_M = 1_737_400.0
MIN_RADIUS_KM, MAX_RADIUS_KM = 0.5, 100.0
MIN_N, MAX_N = 9, 401
DEFAULT_MAX_N = 301  # ≈ 90 тис. вузлів, ≈ 480 КБ у base64


def default_radius_km(resolution_m: float) -> float:
    """Радіус за роздільністю DEM: де DEM дрібний, показуємо ближню зону; де грубий — ширшу."""
    if resolution_m <= 0:
        return 5.0
    if resolution_m <= 30:
        return 5.0
    if resolution_m <= 100:
        return 10.0
    if resolution_m <= 600:
        return 30.0
    return 60.0


def default_n(radius_km: float, resolution_m: float) -> int:
    """Крок сітки ≈ роздільності DEM (дрібніше за DEM немає сенсу), непарне, 33…301."""
    if resolution_m <= 0:
        return 33
    n = max(33, min(DEFAULT_MAX_N, round(2 * radius_km * 1000.0 / resolution_m) + 1))
    return n if n % 2 else n + 1  # межа 301 непарна, тож парне n ≤ 300 → n + 1 ≤ 301


def _grid_latlon(lat: float, lon: float, radius_m: float, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Широта й довгота вузлів n × n: рядок i — на північ, стовпець j — на схід."""
    east, north, up = frames.enu_basis(lat, lon)
    idx = (np.arange(n) - (n - 1) / 2.0) * (2.0 * radius_m / (n - 1))
    e, nn = np.meshgrid(idx, idx)
    pos = R_MOON_M * up + e[..., None] * east + nn[..., None] * north
    return frames.vector_to_latlon(pos)


@lru_cache(maxsize=16)
def _patch(dems: tuple, lat: float, lon: float, radius_km: float, n: int) -> dict:
    spacing = 2.0 * radius_km * 1000.0 / (n - 1)
    flat = {
        "lat": lat, "lon": (lon + 180.0) % 360.0 - 180.0, "radius_km": radius_km, "n": n,
        "spacing_m": round(spacing, 3), "ground_height_m": 0.0, "source": "flat", "resolution_m": 0.0,
        "sources": [], "encoding": "float32-le-base64",
    }
    center = next((d for d in dems if d.covers(lat, lon)), None)
    if center is None:
        heights = np.zeros((n, n), dtype="<f4")
        return {**flat, "heights_b64": base64.b64encode(heights.tobytes()).decode("ascii"),
                "min_height_m": 0.0, "max_height_m": 0.0, "missing_fraction": 0.0 if not dems else 1.0}

    lat_g, lon_g = _grid_latlon(lat, lon, radius_km * 1000.0, n)
    h = np.full((n, n), np.nan)
    used: list[str] = []
    for dem in dems:  # від найдетальнішого: у кожному вузлі — найкращий DEM, що його покриває
        m = np.isnan(h) & dem.covers_many(lat_g, lon_g)
        if m.any():
            h[m] = dem(lat_g[m], lon_g[m])
            used.append(dem.id)
    ground = float(h[(n - 1) // 2, (n - 1) // 2])
    if np.isnan(ground):
        ground = float(center(lat, lon))
    missing = float(np.isnan(h).mean())
    rel = np.where(np.isnan(h), 0.0, h - ground).astype("<f4")
    return {
        **flat, "ground_height_m": round(ground, 1), "source": center.id, "resolution_m": center.resolution_m,
        "sources": used, "heights_b64": base64.b64encode(rel.tobytes()).decode("ascii"),
        "min_height_m": round(float(rel.min()), 1), "max_height_m": round(float(rel.max()), 1),
        "missing_fraction": round(missing, 4),
    }


def terrain_patch(lat: float, lon: float, radius_km: float | None = None, n: int | None = None) -> dict:
    """Сітка висот навколо точки. radius_km й n — за замовчуванням з роздільності найдетальнішого DEM у точці."""
    dems = elevation.available()
    res = next((d.resolution_m for d in dems if d.covers(lat, lon)), 0.0)
    radius = default_radius_km(res) if radius_km is None else float(radius_km)
    count = default_n(radius, res) if n is None else int(n)
    return _patch(dems, round(lat, 5), round(lon, 5), round(radius, 3), count)
