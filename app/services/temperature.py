"""Температура поверхні Місяця з вимірювань LRO Diviner (дані готує tools/build_temperature_data.py).

GCP (Williams et al. 2017): болометрична температура в комірках 0,5° за місцевим часом (бін 15 хв),
усі вимірювання 2009–2015. «Температура на дату» — значення для місцевого сонячного часу кожної
комірки в цей момент: LT = 12 год + (довгота − довгота підсонячної точки) / 15° (DE440 + IAU 2015).
Сезони не розділено: це середнє вимірювань для даного місцевого часу.

PRP (Paige et al. 2010): південний полюс, ~0,5 км — річні середня й максимальна температура та
глибина, з якої водяний лід стабільний.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import numpy as np
from flask import current_app

from app.core import frames
from app.core.ephemeris import get_ephemeris

# Кодування для текстури: код 0 — немає даних; значення = OFFSET + (код − 1) · SCALE
T_OFFSET_K, T_SCALE_K = 20.0, 1.5  # 20…401 K, крок 1,5 K
R_MOON_M = 1_737_400.0

GCP_URL = "https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_gcp/"
PRP_URL = "https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_prp/"

KINDS = {
    "now": ("Температура поверхні на {dt} (Diviner, за місцевим часом)", (40.0, 400.0)),
    "max": ("Максимальна температура за місячну добу (Diviner GCP, 0,5°)", (100.0, 400.0)),
    "min": ("Мінімальна температура за місячну добу (Diviner GCP, 0,5°)", (20.0, 130.0)),
    "mean": ("Середня температура за місячну добу (Diviner GCP, 0,5°)", (40.0, 250.0)),
    "prp_max": ("Річна максимальна температура, південний полюс (Diviner PRP, 0,5 км)", (30.0, 330.0)),
    "prp_avg": ("Річна середня температура, південний полюс (Diviner PRP, 0,5 км)", (25.0, 230.0)),
    "ice_depth": ("Глибина, з якої водяний лід стабільний (Diviner PRP, 0,5 км)", None),
}

NOTE_GCP_NOW = ("Середнє вимірювань Diviner 2009–2015 для місцевого часу кожної комірки 0,5° (бін 15 хв); "
                "сезонні відмінності не розділено — біля полюсів вони суттєві. Прогалини до 2 год заповнено "
                "інтерполяцією, довші — без кольору.")
NOTE_GCP_STATS = ("Статистика за всіма бінами місцевого часу комірки (вимірювання 2009–2015). "
                  "Без кольору — немає вимірювань.")
NOTE_PRP = ("Модель теплового балансу з рельєфом LOLA, узгоджена з вимірюваннями Diviner (Paige et al. 2010). "
            "Продукт — квадрат 600 × 600 км навколо полюса; показуємо вписане коло радіусом 300 км "
            "(південніше 80,1° пд., межа — світла лінія), щоб покриття було однаковим в усіх напрямках. "
            "Поза колом — без кольору.")
NOTE_ICE = (NOTE_PRP + " Глибина, на якій водяний лід сублімує не швидше 1 кг/м² за мільярд років. "
            "0 м — лід стабільний на поверхні (холодні пастки); без кольору — глибше 2,87 м.")


@dataclass(frozen=True)
class TempData:
    meta: dict
    tbol: np.ndarray  # uint16 [lat, lon, lt], 0,1 K
    filled: np.ndarray
    stats: dict
    prp: dict | None

    @property
    def res_deg(self) -> float:
        return 180.0 / self.tbol.shape[0]

    @property
    def lt_step_h(self) -> float:
        return 24.0 / self.tbol.shape[2]


@lru_cache(maxsize=2)
def _load(temp_dir: str, signature: tuple) -> TempData:
    d = Path(temp_dir)
    meta = json.loads((d / "temperature.json").read_text(encoding="utf-8"))
    tbol = np.load(d / "gcp_tbol.npy", mmap_mode="r")
    filled = np.load(d / "gcp_tbol_filled.npy", mmap_mode="r")
    stats = dict(np.load(d / "gcp_stats.npz"))
    prp = dict(np.load(d / "prp_south.npz")) if (d / "prp_south.npz").exists() else None
    return TempData(meta, tbol, filled, stats, prp)


def data() -> TempData:
    d = Path(current_app.config["TEMP_DIR"])
    files = ["temperature.json", "gcp_tbol.npy", "gcp_tbol_filled.npy", "gcp_stats.npz", "prp_south.npz"]
    if not all((d / f).exists() for f in files[:4]):
        raise RuntimeError("Немає даних Diviner: запустіть python tools/build_temperature_data.py")
    signature = tuple((f, (d / f).stat().st_mtime) for f in files if (d / f).exists())
    return _load(str(d), signature)


def sub_solar_lon(when: datetime) -> float:
    eph = get_ephemeris()
    _, lon = frames.vector_to_latlon(eph.sun_vector_me(eph.time(when)))
    return float(lon)


def local_time_h(lon, sub_lon: float):
    """Місцевий сонячний час, год: полудень — на довготі підсонячної точки, на схід — пізніше."""
    return (12.0 + (np.asarray(lon, dtype=float) - sub_lon) / 15.0) % 24.0


def _interp_lt(series: np.ndarray, lt, step_h: float) -> np.ndarray:
    """Значення (0,1 K, 0 — немає) за місцевим часом: лінійно між сусідніми бінами по колу доби.

    series — [..., n_lt]; lt — місцевий час тієї ж форми, що й series[..., 0].
    Якщо один із сусідніх бінів порожній — беремо найближчий, лише якщо саме він є.
    """
    n_lt = series.shape[-1]
    p = np.asarray(lt, dtype=float) / step_h - 0.5  # центри бінів — у (k + 0,5) · step
    k0 = np.floor(p).astype(int) % n_lt
    k1 = (k0 + 1) % n_lt
    w = p - np.floor(p)
    v0 = np.take_along_axis(series, k0[..., None], axis=-1)[..., 0].astype(np.float64)
    v1 = np.take_along_axis(series, k1[..., None], axis=-1)[..., 0].astype(np.float64)
    both = (v0 > 0) & (v1 > 0)
    out = np.where(both, v0 * (1 - w) + v1 * w, 0.0)
    out = np.where(~both & (v0 > 0) & (w < 0.5), v0, out)
    return np.where(~both & (v1 > 0) & (w >= 0.5), v1, out)


def _codes(values: np.ndarray, offset: float, scale: float) -> np.ndarray:
    """Коди 1…255 для скінченних значень, 0 — для NaN (немає даних)."""
    v = np.asarray(values, dtype=np.float64)
    ok = np.isfinite(v)
    codes = np.clip(np.round((np.where(ok, v, offset) - offset) / scale) + 1, 1, 255)
    return np.where(ok, codes, 0).astype(np.uint8)


def temperature_map(kind: str, when: datetime) -> dict:
    if kind not in KINDS:
        raise ValueError(f"Невідомий показник: {kind}")
    td = data()
    title, rng = KINDS[kind]
    out = {"kind": kind, "datetime": when.strftime("%Y-%m-%dT%H:%M:%SZ")}
    if kind in ("now", "max", "min", "mean"):
        n_lat, n_lon, _ = td.tbol.shape
        if kind == "now":
            sub = sub_solar_lon(when)
            lon_c = -180.0 + (np.arange(n_lon) + 0.5) * td.res_deg
            lt = np.broadcast_to(local_time_h(lon_c, sub), (n_lat, n_lon))
            values = _interp_lt(np.asarray(td.filled), lt, td.lt_step_h) / 10.0
            values[values <= 0] = np.nan
            out.update(sub_solar_lon=round(sub, 3), note=NOTE_GCP_NOW)
        else:
            values = td.stats[f"{kind}_k"]
            out["note"] = NOTE_GCP_STATS
        codes = _codes(values, T_OFFSET_K, T_SCALE_K)
        out.update(projection="equirectangular", width=n_lon, height=n_lat, units="K",
                   source={"name": "LRO Diviner GCP", "url": GCP_URL, "reference": td.meta["gcp"]["reference"]})
        code = (T_OFFSET_K, T_SCALE_K)
    else:
        if td.prp is None:
            raise RuntimeError("Немає полярного продукту Diviner PRP: запустіть tools/build_temperature_data.py")
        n = td.prp["avg_k"].shape[0]
        half = td.meta["prp_south"]["half_extent_m"]
        # вписане коло: центри комірок далі за half від полюса — без даних
        c = (np.arange(n) + 0.5) / n * 2 * half - half
        outside = np.hypot(c[None, :], c[:, None]) > half
        if kind == "ice_depth":
            depth = td.prp["ice_depth_m"]
            dmax = float(np.nanmax(depth)) if np.isfinite(depth).any() else 1.0
            scale = max(0.01, dmax / 254.0)
            codes = _codes(np.where(outside, np.nan, depth), 0.0, scale)
            code, rng, units, note = (0.0, scale), (0.0, round(dmax, 2)), "m", NOTE_ICE
        else:
            values = td.prp["max_k" if kind == "prp_max" else "avg_k"]
            codes = _codes(np.where(outside, np.nan, values), T_OFFSET_K, T_SCALE_K)
            code, units, note = (T_OFFSET_K, T_SCALE_K), "K", NOTE_PRP
        out.update(projection="south_polar_stereographic", width=n, height=n, half_extent_m=half, units=units,
                   note=note, source={"name": "LRO Diviner PRP (південь)", "url": PRP_URL,
                                      "reference": td.meta["prp_south"]["reference"]})
    out.update(title=title.format(dt=out["datetime"].replace("T", " ")), range=list(rng),
               code={"offset": code[0], "scale": code[1]},
               codes_b64=base64.b64encode(np.ascontiguousarray(codes).tobytes()).decode("ascii"))
    return out


def _prp_at(td: TempData, lat: float, lon: float) -> dict | None:
    if td.prp is None or lat > -60:
        return None
    meta = td.meta["prp_south"]
    n, half = td.prp["avg_k"].shape[0], meta["half_extent_m"]
    r = 2.0 * R_MOON_M * np.tan(np.radians(90.0 - abs(lat)) / 2.0)
    x, y = r * np.sin(np.radians(lon)), r * np.cos(np.radians(lon))
    if np.hypot(x, y) > half:  # той самий обріз, що й на мапі
        return None
    col, row = int((x + half) / (2 * half) * n), int((y + half) / (2 * half) * n)
    if not (0 <= col < n and 0 <= row < n):
        return None
    avg, mx, ice = (float(td.prp[k][row, col]) for k in ("avg_k", "max_k", "ice_depth_m"))
    if not np.isfinite(avg):
        return None
    return {"avg_k": round(avg, 1), "max_k": round(mx, 1),
            "ice_depth_m": round(ice, 3) if np.isfinite(ice) else None, "cell_m": meta["cell_m"]}


def temperature_point(lat: float, lon: float, when: datetime) -> dict:
    td = data()
    lon = (lon + 180.0) % 360.0 - 180.0
    n_lat, n_lon, n_lt = td.tbol.shape
    i = min(n_lat - 1, max(0, int((lat + 90.0) / td.res_deg)))
    j = min(n_lon - 1, max(0, int((lon + 180.0) / td.res_deg)))
    sub = sub_solar_lon(when)
    lt = float(local_time_h(lon, sub))
    raw = np.asarray(td.tbol[i, j], dtype=np.float64) / 10.0
    now = float(_interp_lt(np.asarray(td.filled[i, j])[None, :], np.array([lt]), td.lt_step_h)[0]) / 10.0
    stat = lambda k: (None if not np.isfinite(td.stats[k][i, j]) else round(float(td.stats[k][i, j]), 1))  # noqa: E731
    return {
        "lat": lat, "lon": lon, "datetime": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "local_time_h": round(lt, 3), "sub_solar_lon": round(sub, 3),
        "now_k": round(now, 1) if now > 0 else None,
        "max_k": stat("max_k"), "min_k": stat("min_k"), "mean_k": stat("mean_k"),
        "diurnal": [{"ltim_h": round((k + 0.5) * td.lt_step_h, 3), "tbol_k": round(float(v), 1) if v > 0 else None}
                    for k, v in enumerate(raw)],
        "cell": {"lat": round(-90.0 + (i + 0.5) * td.res_deg, 3), "lon": round(-180.0 + (j + 0.5) * td.res_deg, 3),
                 "res_deg": td.res_deg},
        "prp": _prp_at(td, lat, lon),
        "source": {"name": "LRO Diviner GCP / PRP", "url": GCP_URL, "reference": td.meta["gcp"]["reference"]},
    }
