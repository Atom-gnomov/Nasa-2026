"""Готує температурні дані LRO Diviner для шару «Температура» (/api/temperature, /api/temperature/map).

Джерела — PDS Geosciences Node, бандл urn:nasa:pds:lro_diviner_derived1 (завантажується в
data_cache/temperature/src/):
    GCP — Global Cumulative Products (Williams et al. 2017, Icarus 283, 300–325): болометрична
          температура TBOL у комірках 0,5° × 0,5° і за місцевим часом кроком 0,25 год, усі надирні
          вимірювання 05.07.2009–01.04.2015. 18 смуг по 10° широти (ASCII, ~156 МБ кожна).
    PRP — Polar Resource Products, південь (Paige et al. 2010, Science 330): трикутна сітка ~0,5 км
          до ~80° пд.: річна середня й річна максимальна температура (модель, узгоджена з Diviner)
          і глибина, на якій водяний лід стабільний.

Вихід (data_cache/temperature/):
    gcp_tbol.npy          — uint16 [широта 360, довгота 720, місц. час 96], 0,1 K; 0 — немає даних.
                            Рядок 0 — пд. смуга −90…−89,5°, стовпець 0 — −180…−179,5°.
    gcp_tbol_filled.npy   — те саме, прогалини в місцевому часі до 2 год заповнено лінійно (по колу доби).
    gcp_stats.npz         — max / min / mean за місячну добу (float32, NaN — немає даних), кількість бінів.
    prp_south.npz         — avg_k, max_k, ice_depth_m (float32 [N, N], NaN — немає) у площині південної
                            полярної стереографічної проєкції (як LOLA dsmap_polar.cat), рядок 0 — низ (−y).
    temperature.json      — опис сіток, джерел і одиниць.

Запуск:  python tools/build_temperature_data.py      (лише numpy; ~3,4 ГБ завантаження, ~2 хв обробки)
"""

from __future__ import annotations

import json
import time
import warnings
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data_cache" / "temperature"
SRC_DIR = OUT_DIR / "src"
BASE = "https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/"
R_MOON_M = 1_737_400.0

BANDS = ["90s80s", "80s70s", "70s60s", "60s50s", "50s40s", "40s30s", "30s20s", "20s10s", "10s00s",
         "00n10n", "10n20n", "20n30n", "30n40n", "40n50n", "50n60n", "60n70n", "70n80n", "80n90n"]
GCP_RES_DEG = 0.5
GCP_LT_STEP_H = 0.25
GAP_FILL_H = 2.0  # заповнюємо прогалини в місцевому часі не довші за 2 год

PRP_CELL_M = 500.0
PRP_HALF_M = 300_000.0  # сітка PRP — квадрат ±300 км навколо полюса


def download(url: str) -> Path:
    path = SRC_DIR / url.rsplit("/", 1)[1]
    if path.exists():
        return path
    SRC_DIR.mkdir(parents=True, exist_ok=True)
    print(f"завантаження {path.name} …", flush=True)
    tmp = path.with_name(path.name + ".part")
    with urllib.request.urlopen(url, timeout=120) as resp, open(tmp, "wb") as f:
        while chunk := resp.read(1 << 22):
            f.write(chunk)
    tmp.replace(path)
    return path


def build_gcp() -> dict:
    n_lat, n_lon, n_lt = int(180 / GCP_RES_DEG), int(360 / GCP_RES_DEG), int(24 / GCP_LT_STEP_H)
    tbol = np.zeros((n_lat, n_lon, n_lt), dtype=np.uint16)
    for band in BANDS:
        path = download(f"{BASE}data_derived_gcp/global_cumul_avg_cyl_{band}_002.tab")
        t0 = time.time()
        # колонки: clon, clat, ltim, t3…t9, tbol; −9999 — немає спостережень
        arr = np.loadtxt(path, delimiter=",", skiprows=1, usecols=(0, 1, 2, 10), dtype=np.float64)
        lon, lat, lt, tb = arr.T
        i = np.floor((lat + 90.0) / GCP_RES_DEG).astype(int)
        j = np.floor((lon + 180.0) / GCP_RES_DEG).astype(int)
        k = np.floor(lt / GCP_LT_STEP_H).astype(int)
        ok = (tb > 0) & (i >= 0) & (i < n_lat) & (j >= 0) & (j < n_lon) & (k >= 0) & (k < n_lt)
        tbol[i[ok], j[ok], k[ok]] = np.clip(np.round(tb[ok] * 10), 1, 65535).astype(np.uint16)
        print(f"  {band}: {len(arr)} рядків, з даними {ok.mean() * 100:.1f}%, {time.time() - t0:.1f} с", flush=True)
    np.save(OUT_DIR / "gcp_tbol.npy", tbol)

    # Статистика за добу — лише по справжніх бінах
    t = tbol.astype(np.float32) / 10.0
    t[tbol == 0] = np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # комірки без жодного вимірювання — NaN
        stats = {"max_k": np.nanmax(t, axis=2), "min_k": np.nanmin(t, axis=2), "mean_k": np.nanmean(t, axis=2),
                 "count": (tbol > 0).sum(axis=2).astype(np.uint8)}
    np.savez_compressed(OUT_DIR / "gcp_stats.npz", **stats)

    # Заповнення коротких прогалин у місцевому часі: лінійно між сусідніми бінами по колу доби
    filled = tbol.copy()
    max_gap = int(round(GAP_FILL_H / GCP_LT_STEP_H))
    flat = filled.reshape(-1, n_lt)
    have = flat > 0
    rows = np.nonzero(have.any(axis=1) & ~have.all(axis=1))[0]
    for r in rows:
        h = np.nonzero(have[r])[0]
        hx = np.concatenate([h - n_lt, h, h + n_lt])
        hv = np.tile(flat[r, h].astype(np.float64), 3)
        miss = np.nonzero(~have[r])[0]
        pos = np.searchsorted(hx, miss)
        gap = hx[pos] - hx[pos - 1] - 1
        fill = gap <= max_gap
        if fill.any():
            flat[r, miss[fill]] = np.round(np.interp(miss[fill], hx, hv)).astype(np.uint16)
    np.save(OUT_DIR / "gcp_tbol_filled.npy", filled)
    coverage = float((tbol > 0).mean())
    print(f"GCP: покриття бінів {coverage * 100:.1f}%, після заповнення {(filled > 0).mean() * 100:.1f}%", flush=True)
    return {"shape": [n_lat, n_lon, n_lt], "res_deg": GCP_RES_DEG, "lt_step_h": GCP_LT_STEP_H,
            "units": "0.1 K", "gap_fill_h": GAP_FILL_H, "coverage": round(coverage, 4),
            "period": "2009-07-05 — 2015-04-01", "reference": "Williams et al. (2017), Icarus 283, 300–325",
            "url": f"{BASE}data_derived_gcp/"}


def build_prp() -> dict:
    path = download(f"{BASE}data_derived_prp/dlre_prp_south.tab")
    download(f"{BASE}data_derived_prp/dlre_prp_south.lbl")
    t0 = time.time()
    # колонки: tri1_x … tri3_z, tri_clon, tri_clat, tri_calt, temp_avg, temp_max, ice_depth (−999 — немає)
    arr = np.loadtxt(path, delimiter=",", skiprows=1, usecols=(9, 10, 12, 13, 14), dtype=np.float64)
    lon, lat, t_avg, t_max, ice = arr.T
    # Площина полярної стереографічної проєкції (dsmap_polar.cat): x праворуч (90° сх.), y угору (0°)
    r = 2.0 * R_MOON_M * np.tan(np.radians(90.0 - np.abs(lat)) / 2.0)
    x, y = r * np.sin(np.radians(lon)), r * np.cos(np.radians(lon))
    n = int(2 * PRP_HALF_M / PRP_CELL_M)
    col = np.floor((x + PRP_HALF_M) / PRP_CELL_M).astype(int)
    row = np.floor((y + PRP_HALF_M) / PRP_CELL_M).astype(int)  # рядок 0 — низ (−y)
    ok = (col >= 0) & (col < n) & (row >= 0) & (row < n)
    cell = row[ok] * n + col[ok]

    def grid(values, valid):
        v = values[ok]
        m = valid[ok]
        s = np.bincount(cell[m], weights=v[m], minlength=n * n)
        c = np.bincount(cell[m], minlength=n * n)
        with np.errstate(invalid="ignore"):
            g = (s / c).astype(np.float32)
        return g.reshape(n, n)

    # ice_depth за міткою: 0 — лід стабільний на поверхні, −999 — глибина > 2,8738 м.
    # У даних є й код −1, якого мітка не описує: він трапляється лише там, де річний максимум
    # 45…101 K (найхолодніші пастки, холодніші за клас «0» зі 101…124 K) — тобто лід стабільний
    # на поверхні. Трактуємо −1 як глибину 0 м.
    ice = np.where(ice == -1.0, 0.0, ice)
    out = {
        "avg_k": grid(t_avg, t_avg > 0),
        "max_k": grid(t_max, t_max > 0),
        "ice_depth_m": grid(ice, ice >= 0),
    }
    np.savez_compressed(OUT_DIR / "prp_south.npz", **out)
    ice_ok = np.isfinite(out["ice_depth_m"])
    print(f"PRP: {len(arr)} трикутників за {time.time() - t0:.0f} с; T сер. {np.nanmin(out['avg_k']):.0f}…"
          f"{np.nanmax(out['avg_k']):.0f} K, макс. {np.nanmin(out['max_k']):.0f}…{np.nanmax(out['max_k']):.0f} K; "
          f"лід стабільний у {ice_ok.mean() * 100:.2f}% комірок, "
          f"глибина до {np.nanmax(out['ice_depth_m']):.2f} м", flush=True)
    return {"size": n, "cell_m": PRP_CELL_M, "half_extent_m": PRP_HALF_M,
            "projection": "south_polar_stereographic (LOLA dsmap_polar.cat)",
            "ice_depth_max_m": float(np.nanmax(out["ice_depth_m"])) if ice_ok.any() else None,
            "ice_depth_codes": "0 і −1 — стабільний на поверхні (−1 — холодні пастки, T_max ≤ ~101 K), "
                               "−999 — глибина > 2,8738 м (нестабільний у межах моделі)",
            "reference": "Paige et al. (2010), Science 330, 479–482", "url": f"{BASE}data_derived_prp/"}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = {"version": int(time.time()), "gcp": build_gcp(), "prp_south": build_prp()}
    (OUT_DIR / "temperature.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"готово: {OUT_DIR}")


if __name__ == "__main__":
    main()
