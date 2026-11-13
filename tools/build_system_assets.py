"""Готує моделі й текстури 3D-виду системи Сонце–Земля–Місяць з NASA 3D Resources.

Джерела (https://science.nasa.gov/3d-resources/):
    Сонце — «Sun 3D Model» (glTF), NASA HEAT:
            https://science.nasa.gov/learn/heat/resource/sun-3d-model/
    Земля — «Earth (A)»: рельєфна карта, розфарбована як суходіл/океан (USGS, NASA/JPL),
            рівнопроміжна проєкція 1440×720, довгота 0° по центру:
            https://science.nasa.gov/3d-resources/earth-a/
    Місяць — текстура CGI Moon Kit, яку вже готує tools/build_globe_textures.py (/assets/globe/color.jpg).

Не використано (і чому):
    «Earth» (Earth.zip) — один Earth.stl 203 МБ для 3D-друку: без кольору, рельєф штучно підсилено,
                          гірські хребти замінено тактильною штриховкою;
    «Earth (B)» — фото диска Землі з Apollo 10 (1969), а не розгорнута карта: на кулю не лягає.

Вихід — data_cache/system/ (віддається сторінкою /assets/system/<файл>):
    sun.glb, earth.jpg, system.json — опис файлів, джерел і подяк.

Запуск:  python tools/build_system_assets.py
"""

from __future__ import annotations

import json
import struct
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data_cache" / "system"

ASSETS = {
    "sun": {
        "file": "sun.glb",
        "url": "https://assets.science.nasa.gov/content/dam/science/psd/solar/2023/09/s/Sun_1_1391000.glb",
        "page": "https://science.nasa.gov/learn/heat/resource/sun-3d-model/",
        "credit": "NASA (HEAT, 3D Resources)",
        "note": "Схематична текстура світіння, не знімок конкретної дати",
    },
    "earth": {
        "file": "earth.jpg",
        "url": "https://assets.science.nasa.gov/content/dam/science/cds/3d/resources/image/earth-(a)/Earth%20(A).jpg",
        "page": "https://science.nasa.gov/3d-resources/earth-a/",
        "credit": "USGS & NASA/Jet Propulsion Laboratory",
        "note": "Рельєф, розфарбований як суходіл/океан (не фото); 1440×720, довгота 0° по центру",
    },
}


def download(url: str, path: Path) -> None:
    if path.exists():
        print(f"є: {path.name}")
        return
    print(f"завантаження {path.name} …", flush=True)
    tmp = path.with_name(path.name + ".part")
    with urllib.request.urlopen(url, timeout=120) as resp, open(tmp, "wb") as f:
        while chunk := resp.read(1 << 20):
            f.write(chunk)
    tmp.replace(path)


def check_glb(path: Path) -> dict:
    """Перевіряє, що файл — glTF 2.0 у бінарному контейнері, і повертає короткий опис."""
    with open(path, "rb") as f:
        magic, version, _ = struct.unpack("<III", f.read(12))
        length, _ = struct.unpack("<II", f.read(8))
        gltf = json.loads(f.read(length))
    if magic != 0x46546C67 or version != 2:
        raise ValueError(f"{path.name}: не GLB 2.0")
    return {"meshes": len(gltf.get("meshes", [])), "images": len(gltf.get("images", [])),
            "generator": gltf.get("asset", {}).get("generator", "")}


def check_jpeg(path: Path) -> dict:
    """Розміри JPEG без сторонніх бібліотек (маркер SOF0/SOF2)."""
    data = path.read_bytes()
    i = 2
    while i < len(data):
        marker, size = data[i + 1], struct.unpack(">H", data[i + 2:i + 4])[0]
        if marker in (0xC0, 0xC2):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            if w != 2 * h:
                raise ValueError(f"{path.name}: {w}×{h} — не рівнопроміжна карта 2:1")
            return {"width": w, "height": h}
        i += 2 + size
    raise ValueError(f"{path.name}: не знайдено розмірів JPEG")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = {"version": int(time.time()), "assets": {}}
    for key, a in ASSETS.items():
        path = OUT_DIR / a["file"]
        download(a["url"], path)
        info = check_glb(path) if path.suffix == ".glb" else check_jpeg(path)
        meta["assets"][key] = {**a, **info, "bytes": path.stat().st_size}
    (OUT_DIR / "system.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"готово: {OUT_DIR}")


if __name__ == "__main__":
    main()
