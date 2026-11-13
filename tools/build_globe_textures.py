"""Готує дані 3D-глобуса Місяця з офіційних джерел NASA.

Джерела (завантажуються автоматично в data_cache/globe/src/):
    Колір  — CGI Moon Kit 2025, NASA SVS 4720 (LROC WAC; південніше 70° — альбедо LOLA):
             https://svs.gsfc.nasa.gov/4720 — карта «для візуалізації, не для науки».
    Рельєф — LOLA GDR, PDS Geosciences Node (lrolol_1xxx), продукти з мітками .LBL:
             LDEM_16 (V3.1, ~1,9 км, глобальний) — сітка вершин і нахили всієї кулі;
             LDEM_80S_80M, LDEM_875S_20M (V2.0) — детальні полярні ділянки;
             LDEM_64 (V3.1, ~474 м) — лише для висоти під курсором (/api/elevation), з --with-ldem64.

Вихід (data_cache/globe/, віддається сторінкою /assets/globe/<файл>):
    color.jpg                 — колір;
    slope.webp                — нахили всієї кулі (R — схід, G — північ; 128 = 0, ±127 = ±SLOPE_SCALE);
    height.bin                — висоти вершин сітки 0,25° (int16 LE, м), рядки з півночі на південь;
    polar_<id>_slope.webp     — нахили полярної ділянки в площині проєкції (R — x/праворуч, G — y/угору);
    polar_<id>_height.bin     — висоти вершин полярної сітки (float32 LE, м), рядки знизу догори;
    globe.json                — опис усіх файлів, джерел і версій продуктів.

Запуск:
    pip install tifffile imagecodecs Pillow numpy
    python tools/build_globe_textures.py [--color 8k] [--with-ldem64]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core.dem import R_MOON_M, CylindricalDem, PolarDem, _bilinear, open_dem  # noqa: E402

SVS_URL = "https://svs.gsfc.nasa.gov/vis/a000000/a004700/a004720/"
PDS_URL = "https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/"
VERTEX_STEP_DEG = 0.25  # крок сітки вершин кулі
SLOPE_SCALE = 1.0  # нахил (tg), що кодується значенням ±127 (45°)
POLAR_TEXTURE = 4096  # сторона текстури нахилів полярної ділянки
POLAR_SEGMENTS = 512  # сегментів сітки вершин полярної ділянки на сторону

POLAR_PRODUCTS = ["ldem_80s_80m", "ldem_875s_20m"]

# Маски горизонту для тіней (docs/MATH.md, §6): для кожного пікселя полярної ділянки —
# кут піднесення рельєфу в HORIZON_AZ напрямках (з урахуванням кривини Місяця).
HORIZON_SIZE = 1024
HORIZON_AZ = 24  # кратне 3: по 3 азимути в каналах RGB одного блоку атласу
HORIZON_MAX_KM = 150.0
HORIZON_GROWTH = 1.06
HORIZON_RANGE_DEG = (-4.0, 28.0)  # кодування 0…255 → крок 0,125°

OUT_DIR = ROOT / "data_cache" / "globe"
SRC_DIR = OUT_DIR / "src"


def download(url: str, name: str) -> Path:
    path = SRC_DIR / name
    if path.exists():
        print(f"є: {name}")
        return path
    SRC_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    print(f"завантаження {name} …", flush=True)
    req = urllib.request.Request(url, headers={"Range": f"bytes={tmp.stat().st_size}-"} if tmp.exists() else {})
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "ab" if tmp.exists() else "wb") as f:
        while chunk := resp.read(1 << 20):
            f.write(chunk)
    tmp.replace(path)
    return path


def download_pds(product: str, kind: str) -> Path:
    download(f"{PDS_URL}{kind}/img/{product}.lbl", f"{product}.lbl")
    download(f"{PDS_URL}{kind}/img/{product}.img", f"{product}.img")
    return SRC_DIR / f"{product}.lbl"


def encode_slope(s: np.ndarray) -> np.ndarray:
    return (128.0 + 127.0 * np.clip(s / SLOPE_SCALE, -1.0, 1.0)).round().astype(np.uint8)


def save_slope(path: Path, a: np.ndarray, b: np.ndarray) -> None:
    rgb = np.stack([encode_slope(a), encode_slope(b), np.full(a.shape, 128, np.uint8)], axis=-1)
    Image.fromarray(rgb, "RGB").save(path, lossless=True, quality=100, method=4)


def build_color(src: Path) -> dict:
    rgb16 = tifffile.imread(src)
    rgb8 = (rgb16.astype(np.float32) / 257.0 + 0.5).clip(0, 255).astype(np.uint8)
    Image.fromarray(rgb8[..., :3], "RGB").save(OUT_DIR / "color.jpg", quality=90, optimize=True)
    h, w = rgb8.shape[:2]
    return {"file": "color.jpg", "width": w, "height": h, "color_space": "srgb", "source": src.name,
            "url": "https://svs.gsfc.nasa.gov/4720", "note": "LROC WAC 70°пн–70°пд; ближче до полюсів — альбедо LOLA"}


def global_heights(dem: CylindricalDem) -> np.ndarray:
    """Висоти (м) у порядку CGI: стовпець 0 — довгота −180°, рядок 0 — 90° пн.

    У PDS стовпець 0 — довгота 0° (CENTER_LONGITUDE = 180), тому зсуваємо на пів ширини.
    """
    h = np.asarray(dem.data, dtype=np.float32) * dem.scale_factor
    return np.roll(h, dem.samples // 2, axis=1)


def build_global_slope(h_m: np.ndarray) -> dict:
    """Нахили на схід і на північ. Біля полюса крок по довготі ~1/cos(lat) пікселів, щоб не підсилювати шум."""
    rows, cols = h_m.shape
    step_rad = np.radians(180.0 / rows)
    lat = np.radians(90.0 - (np.arange(rows) + 0.5) * 180.0 / rows)
    dy_north = R_MOON_M * step_rad
    east = np.empty_like(h_m)
    for i in range(rows):
        cos_lat = max(np.cos(lat[i]), 1e-6)
        k = int(min(cols // 4, max(1, round(1.0 / cos_lat))))
        east[i] = (np.roll(h_m[i], -k) - np.roll(h_m[i], k)) / (2.0 * R_MOON_M * step_rad * cos_lat * k)
    padded = np.pad(h_m, ((1, 1), (0, 0)), mode="edge")
    north = (padded[:-2] - padded[2:]) / (2.0 * dy_north)
    save_slope(OUT_DIR / "slope.webp", east, north)
    return {"file": "slope.webp", "width": cols, "height": rows, "encoding": "R=east, G=north; slope=(v-128)/127*scale",
            "slope_scale": SLOPE_SCALE}


def build_vertex_heights(h_m: np.ndarray) -> dict:
    """Середнє висот навколо кожної вершини сітки VERTEX_STEP_DEG (з дубльованим швом −180/+180)."""
    rows, cols = h_m.shape
    k = int(round(VERTEX_STEP_DEG * cols / 360.0))
    half = k // 2
    padded = np.roll(np.pad(h_m, ((half, half), (0, 0)), mode="edge"), half, axis=1)
    n_lat, n_lon = rows // k + 1, cols // k
    blocks = padded[: n_lat * k].reshape(n_lat, k, n_lon, k).mean(axis=(1, 3))
    blocks[0, :] = blocks[0].mean()
    blocks[-1, :] = blocks[-1].mean()
    grid = np.concatenate([blocks, blocks[:, :1]], axis=1)
    grid.round().astype("<i2").tofile(OUT_DIR / "height.bin")
    return {"file": "height.bin", "lon_count": grid.shape[1], "lat_count": grid.shape[0],
            "step_deg": VERTEX_STEP_DEG, "dtype": "int16-le", "units": "m",
            "min_m": float(grid.min()), "max_m": float(grid.max())}


class PolarSampler:
    """Висота в точці площини полярної проєкції (м): найдетальніший продукт, що покриває точку."""

    def __init__(self, dems: list[PolarDem]):
        self.layers = [(d, np.asarray(d.data, dtype=np.float32) * d.scale_factor)
                       for d in sorted(dems, key=lambda d: d.map_scale_m)]

    def __call__(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        out = np.full(x.shape, np.nan, dtype=np.float64)
        for i, (dem, arr) in enumerate(self.layers):
            n, s = dem.lines, dem.map_scale_m
            lim = n * s / 2 - s
            last = i == len(self.layers) - 1
            m = np.isnan(out) if last else np.isnan(out) & (np.abs(x) < lim) & (np.abs(y) < lim)
            if m.any():
                out[m] = _bilinear(arr, -y[m] / s + n / 2 - 0.5, x[m] / s + n / 2 - 0.5, wrap_cols=False)
        return out


def build_horizon_atlas(dem: PolarDem, sampler: PolarSampler) -> dict:
    """Атлас масок горизонту: блоки HORIZON_SIZE² по 3 азимути (R, G, B), блок 0 — угорі.

    Азимут — від локальної півночі (на південному полюсі — назовні від полюса) за годинниковою
    стрілкою, як у app.core.frames. Кут = max atan((h − h₀ − d²/2R) / d) уздовж променя.
    """
    size = HORIZON_SIZE
    half = dem.lines * dem.map_scale_m / 2.0
    px = 2 * half / size
    coord = (np.arange(size) - size / 2 + 0.5) * px
    xx, yy = np.meshgrid(coord, coord[::-1])  # рядок 0 — угорі (+y)
    h0 = sampler(xx, yy)
    lon = np.arctan2(xx, yy)
    north = (np.sin(lon), np.cos(lon))
    east = (np.cos(lon), -np.sin(lon))
    dists = [px]
    while dists[-1] < HORIZON_MAX_KM * 1000:
        dists.append(dists[-1] * HORIZON_GROWTH + px * 0.5)
    lo, hi = HORIZON_RANGE_DEG
    blocks = []
    for a in range(HORIZON_AZ):
        az = 2 * np.pi * a / HORIZON_AZ
        dx = np.cos(az) * north[0] + np.sin(az) * east[0]
        dy = np.cos(az) * north[1] + np.sin(az) * east[1]
        best = np.full(xx.shape, -np.inf)
        for d in dists:
            h = sampler(xx + d * dx, yy + d * dy)
            np.maximum(best, (h - h0 - d * d / (2 * R_MOON_M)) / d, out=best)
        ang = np.degrees(np.arctan(best))
        blocks.append(np.clip(np.round((ang - lo) / (hi - lo) * 255), 0, 255).astype(np.uint8))
        print(f"  горизонт {a + 1}/{HORIZON_AZ}", flush=True)
    atlas = np.concatenate([np.stack(blocks[i:i + 3], axis=-1) for i in range(0, HORIZON_AZ, 3)], axis=0)
    file = f"polar_{dem.id}_horizon.webp"
    Image.fromarray(atlas, "RGB").save(OUT_DIR / file, lossless=True, quality=100, method=4)
    return {"file": file, "size": size, "azimuths": HORIZON_AZ, "blocks": HORIZON_AZ // 3,
            "range_deg": list(HORIZON_RANGE_DEG), "max_distance_km": HORIZON_MAX_KM,
            "layout": "блоки по вертикалі, блок 0 угорі; у блоці R,G,B — азимути 3b, 3b+1, 3b+2"}


def build_polar_tile(dem: PolarDem) -> dict:
    """Детальна полярна ділянка: нахили в площині проєкції + сітка висот вершин.

    Площина — як у dsmap_polar.cat: x праворуч (90° сх.), y угору (0°). Нахил по землі =
    k · dh/ds_карти, де k = 2 / (1 + sin|φ|) — масштаб стереографічної проєкції (Snyder 1987).
    """
    n, s = dem.lines, dem.map_scale_m
    h = np.asarray(dem.data, dtype=np.float32) * dem.scale_factor
    half_m = n * s / 2.0
    # координати центрів пікселів у метрах (рядок 0 — угорі, +y)
    coord = ((np.arange(n) - n / 2 + 0.5) * s).astype(np.float32)
    gx = np.gradient(h, s, axis=1).astype(np.float32)
    gy = (-np.gradient(h, s, axis=0)).astype(np.float32)
    del h
    k = np.hypot(coord[None, :], coord[:, None])  # відстань від полюса в площині, м (float32)
    k *= 0.5 / R_MOON_M
    np.arctan(k, out=k)
    k *= 2.0  # колатитуда
    np.cos(k, out=k)  # sin|φ|
    k += 1.0
    np.divide(2.0, k, out=k)  # масштаб проєкції
    gx *= k
    gy *= k
    del k
    t = POLAR_TEXTURE
    sx = np.asarray(Image.fromarray(gx.astype(np.float32), "F").resize((t, t), Image.BOX))
    sy = np.asarray(Image.fromarray(gy.astype(np.float32), "F").resize((t, t), Image.BOX))
    slope_file = f"polar_{dem.id}_slope.webp"
    save_slope(OUT_DIR / slope_file, sx, sy)

    # Вершини: точна білінійна вибірка в позиціях вершин (рядки знизу догори, як v у WebGL)
    v = POLAR_SEGMENTS
    pos = np.linspace(-half_m, half_m, v + 1)
    vx, vy = np.meshgrid(pos, pos)  # рядок 0 — найменший y (низ)
    col = vx / s + n / 2 - 0.5
    row = -vy / s + n / 2 - 0.5
    heights = _bilinear(dem.data, row, col, wrap_cols=False) * dem.scale_factor
    height_file = f"polar_{dem.id}_height.bin"
    heights.astype("<f4").tofile(OUT_DIR / height_file)
    return {
        "id": dem.id, "product_version": dem.version, "resolution_m": s, "edge_lat": dem.edge_lat,
        "half_extent_m": half_m, "slope": {"file": slope_file, "size": t, "slope_scale": SLOPE_SCALE,
                                           "encoding": "R=x (праворуч, 90°E), G=y (угору, 0°)"},
        "height": {"file": height_file, "segments": v, "dtype": "float32-le", "units": "m",
                   "rows": "знизу догори (−y → +y)", "min_m": float(heights.min()), "max_m": float(heights.max())},
        "url": f"{PDS_URL}polar/img/{dem.path.name}",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--color", choices=["4k", "8k", "16k"], default="4k")
    parser.add_argument("--with-ldem64", action="store_true", help="завантажити LDEM_64 (530 МБ) для /api/elevation")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    color_src = download(f"{SVS_URL}lroc_color_16bit_srgb_{args.color}.tif", f"lroc_color_16bit_srgb_{args.color}.tif")
    global_dem = open_dem(download_pds("ldem_16", "cylindrical"))
    polar_dems = [open_dem(download_pds(p, "polar")) for p in POLAR_PRODUCTS]
    if args.with_ldem64:
        download_pds("ldem_64", "cylindrical")

    print("колір …", flush=True)
    color = build_color(color_src)
    print("рельєф кулі …", flush=True)
    h_m = global_heights(global_dem)
    meta = {
        "version": int(time.time()),
        "radius_km": R_MOON_M / 1000.0,
        "frame": "MEAN EARTH/POLAR AXIS (LOLA)",
        "projection": "equirectangular, lon −180…180 зліва направо, lat 90…−90 згори вниз",
        "credit": "NASA SVS CGI Moon Kit; LRO LOLA GDR (PDS Geosciences Node); LRO LROC WAC",
        "color": color,
        "relief_source": {**global_dem.describe(), "url": f"{PDS_URL}cylindrical/img/{global_dem.path.name}"},
        "slope": build_global_slope(h_m),
        "height": build_vertex_heights(h_m),
        "polar_tiles": [],
    }
    del h_m
    for dem in sorted(polar_dems, key=lambda d: -d.resolution_m):  # від грубішої до детальнішої
        print(f"полярна ділянка {dem.id} …", flush=True)
        meta["polar_tiles"].append(build_polar_tile(dem))
    sampler = PolarSampler(polar_dems)
    for tile, dem in zip(meta["polar_tiles"], sorted(polar_dems, key=lambda d: -d.resolution_m), strict=True):
        print(f"маски горизонту {dem.id} …", flush=True)
        tile["horizon"] = build_horizon_atlas(dem, sampler)
    (OUT_DIR / "globe.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"готово: {OUT_DIR}")


if __name__ == "__main__":
    main()
