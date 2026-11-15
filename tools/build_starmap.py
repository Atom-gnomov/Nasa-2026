"""Готує справжнє зоряне небо для фону: NASA SVS «Deep Star Maps 2020» → легкий JPEG.

Джерело (NASA/Goddard Space Flight Center Scientific Visualization Studio, візуалізатор Ernie Wright):
    https://svs.gsfc.nasa.gov/4851
    starmap_2020_4k.exr — 4096×2048, рівнопроміжна проєкція в небесних координатах ICRF/J2000 (пряме сходження
    збільшується ліворуч, 0h по центру); 1,7 млрд зір з каталогів Hipparcos-2, Tycho-2 і Gaia DR2.
Подяка (вимога джерела): NASA/Goddard Space Flight Center Scientific Visualization Studio. Gaia DR2: ESA/Gaia/DPAC.

Вихід — data_cache/starmap/ (віддається сторінкою /assets/starmap/<файл>):
    starmap.jpg — 4096×2048, тональне стиснення HDR → 8 біт (зорі лишаються точками, Чумацький Шлях — смугою);
    starmap.json — опис: джерело, розмір, подяка, спосіб тонального перетворення.
Сирий EXR (≈ 34 МБ) лежить у data_cache/starmap/src/ і в git не потрапляє.

Залежності лише для цього скрипта (не для вебзастосунку): OpenEXR, numpy, Pillow.
    pip install OpenEXR numpy Pillow
Запуск:  python tools/build_starmap.py
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data_cache" / "starmap"
SRC_DIR = OUT_DIR / "src"
URL = "https://svs.gsfc.nasa.gov/vis/a000000/a004800/a004851/starmap_2020_4k.exr"
PAGE = "https://svs.gsfc.nasa.gov/4851"
EXR = SRC_DIR / "starmap_2020_4k.exr"
JPG = OUT_DIR / "starmap.jpg"
CREDIT = "NASA/Goddard Space Flight Center Scientific Visualization Studio. Gaia DR2: ESA/Gaia/DPAC."


def download(url: str, path: Path) -> None:
    if path.exists():
        print(f"є: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"завантаження {path.name} …", flush=True)
    tmp = path.with_name(path.name + ".part")
    with urllib.request.urlopen(url, timeout=180) as resp, open(tmp, "wb") as f:
        while chunk := resp.read(1 << 20):
            f.write(chunk)
    tmp.replace(path)


def read_exr(path: Path):
    """Лінійні RGB (float32, висота × ширина × 3) з EXR."""
    import numpy as np
    import OpenEXR

    with OpenEXR.File(str(path)) as f:
        channels = f.channels()
        if "RGB" in channels:
            data = channels["RGB"].pixels
        else:
            data = np.stack([channels[c].pixels for c in ("R", "G", "B")], axis=-1)
    return np.asarray(data, dtype=np.float32)


def tonemap(rgb, exposure: float = 1.0):
    """HDR → [0, 1]: обернена гіперболічна (asinh) шкала з «колінцем»; спершу кліпуємо від'ємні шуми.

    asinh не душить слабку смугу Чумацького Шляху (як лінійне стиснення) і не роздуває яскраві зорі (як гама).
    """
    import numpy as np

    x = np.clip(rgb * exposure, 0.0, None)
    k = 40.0  # крутизна: більше — світліша слабка структура
    y = np.arcsinh(k * x) / np.arcsinh(k * 1.0)
    return np.clip(y, 0.0, 1.0)


def main() -> None:
    import numpy as np
    from PIL import Image

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    download(URL, EXR)
    rgb = read_exr(EXR)
    h, w, _ = rgb.shape
    peak = float(np.percentile(rgb, 99.99))
    print(f"EXR {w}×{h}; 99,99-й перцентиль яскравості {peak:.3g}")
    img = (tonemap(rgb) * 255.0 + 0.5).astype(np.uint8)
    Image.fromarray(img, "RGB").save(JPG, quality=90, optimize=True, progressive=True)
    meta = {
        "file": JPG.name, "width": w, "height": h,
        "projection": "plate carrée, ICRF/J2000; пряме сходження збільшується ліворуч, 0h по центру; північ угорі",
        "source": {"page": PAGE, "url": URL, "title": "Deep Star Maps 2020 (SVS 4851)",
                   "stars": "Hipparcos-2, Tycho-2, Gaia DR2 (≈ 1,7 млрд зір)"},
        "credit": CREDIT,
        "tonemap": "asinh(40·x)/asinh(40), x — лінійна яскравість EXR",
        "bytes": JPG.stat().st_size,
        "built": time.strftime("%Y-%m-%d"),
    }
    (OUT_DIR / "starmap.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"готово: {JPG.name}, {meta['bytes'] / 1e6:.2f} МБ")


if __name__ == "__main__":
    main()
