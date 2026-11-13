"""Висота поверхні в точці з найдетальнішого доступного DEM LOLA (app.core.dem).

Пріоритет — найменший крок сітки серед продуктів, що покривають точку:
LDEM_875S_20M (20 м) → LDEM_80S_80M (80 м) → LDEM_64 (~474 м) → LDEM_16 (~1,9 км).
Файли лежать у DEM_DIR (за замовчуванням data_cache/globe/src), їх завантажує
tools/build_globe_textures.py з PDS Geosciences Node.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
from flask import current_app

from app.core import frames
from app.core.dem import R_MOON_M, PdsDem, open_dem

PDS_BASE = "https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/"


@lru_cache(maxsize=4)
def _load(dem_dir: str, signature: tuple) -> tuple[PdsDem, ...]:
    """signature — імена й розміри файлів: докачаний файл підхоплюється без перезапуску."""
    dems = []
    for lbl in sorted(Path(dem_dir).glob("ldem_*.lbl")):
        try:
            dem = open_dem(lbl)
            _ = dem.data  # перевіряє розмір файлу
        except (OSError, ValueError, KeyError):
            continue  # неповне завантаження чи інший формат — пропускаємо
        dems.append(dem)
    return tuple(sorted(dems, key=lambda d: d.resolution_m))


def available() -> tuple[PdsDem, ...]:
    dem_dir = Path(current_app.config["DEM_DIR"])
    signature = tuple((p.name, p.stat().st_size) for p in sorted(dem_dir.glob("ldem_*.img")))
    return _load(str(dem_dir), signature)


def source_url(dem: PdsDem) -> str:
    sub = "polar" if dem.label.get("MAP_PROJECTION_TYPE") == "POLAR STEREOGRAPHIC" else "cylindrical"
    return f"{PDS_BASE}{sub}/img/{dem.path.name}"


def slope_aspect(dem: PdsDem, lat: float, lon: float) -> tuple[float, float, float]:
    """Нахил (°), експозиція (азимут схилу вниз, ° від півночі за годинниковою) і база різниць (м).

    Висоти беремо в чотирьох точках на відстані d уздовж місцевих сходу й півночі — по великому
    колу через вектори (працює й на самому полюсі, де «північ» — напрямок на меридіан lon).
    d = 2 кроки DEM, тобто нахил осереднено на базі 4 пікселів.
    """
    d = 2.0 * max(dem.resolution_m, 5.0)
    delta = d / R_MOON_M
    east, north, up = frames.enu_basis(lat, lon)

    def h_at(direction):
        q = np.cos(delta) * up + np.sin(delta) * direction
        la, lo = frames.vector_to_latlon(q)
        return float(dem(la, lo))

    gx = (h_at(east) - h_at(-east)) / (2 * d)  # dh/dx на схід
    gy = (h_at(north) - h_at(-north)) / (2 * d)  # dh/dy на північ
    slope = float(np.degrees(np.arctan(np.hypot(gx, gy))))
    aspect = float(np.degrees(np.arctan2(-gx, -gy)) % 360.0)  # куди «дивиться» схил (униз)
    return slope, aspect, 2 * d


def elevation(lat: float, lon: float) -> dict:
    """Висота над сферою 1737,4 км, нахил і експозиція схилу, джерело. RuntimeError — якщо DEM немає."""
    for dem in available():
        if dem.covers(lat, lon):
            h = float(dem(lat, lon))
            slope, aspect, base = slope_aspect(dem, lat, lon)
            return {
                "lat": lat,
                "lon": (lon + 180.0) % 360.0 - 180.0,
                "height_m": round(h, 1),
                "radius_km": round((R_MOON_M + h) / 1000.0, 4),
                "slope_deg": round(slope, 2),
                "aspect_deg": round(aspect, 1),
                "slope_baseline_m": round(base, 1),
                "source": {**dem.describe(), "url": source_url(dem)},
            }
    raise RuntimeError("Немає DEM LOLA: запустіть python tools/build_globe_textures.py")
