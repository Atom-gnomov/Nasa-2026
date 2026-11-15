"""Імпорт панорами неба з GLB (tools/import_sky_pano.py): читання GLB, витяг текстури, подяка, калібрування.

Тести працюють на синтетичному GLB, зібраному в тесті: справжній файл у репозиторій не додаємо
(ліцензія CC BY-NC-SA 4.0).
Потрібні numpy і Pillow (лише для цього інструмента); без Pillow тести пропускаються.
"""

import importlib.util
import json
import struct
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest

image_mod = pytest.importorskip("PIL.Image")

ROOT = Path(__file__).resolve().parents[1]


def _tool():
    spec = importlib.util.spec_from_file_location("import_sky_pano", ROOT / "tools" / "import_sky_pano.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _jpeg(width: int, height: int, pixels=None) -> bytes:
    img = image_mod.new("RGB", (width, height), (10, 10, 20)) if pixels is None else image_mod.fromarray(pixels, "RGB")
    buf = BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _glb(texture: bytes, mime="image/jpeg", with_credit=True) -> bytes:
    pad = (-len(texture)) % 4
    binary = texture + b"\0" * pad
    js = {
        "asset": {"version": "2.0", "extras": {
            "title": "Sky Pano - Milkyway", "author": "MozillaHubs (https://sketchfab.com/mozillareality)",
            "license": "CC-BY-NC-SA-4.0 (http://creativecommons.org/licenses/by-nc-sa/4.0/)",
            "source": "https://sketchfab.com/3d-models/sky-pano-milkyway-0016725c047a4ea18cd0b5e5ef2fe441",
        } if with_credit else {}},
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(texture)}],
        "images": [{"bufferView": 0, "mimeType": mime}],
    }
    jb = json.dumps(js).encode("utf-8")
    jb += b" " * ((-len(jb)) % 4)
    body = struct.pack("<II", len(jb), 0x4E4F534A) + jb + struct.pack("<II", len(binary), 0x004E4942) + binary
    return b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body


def test_import_extracts_texture_and_credit(tmp_path):
    tool = _tool()
    texture = _jpeg(256, 128)
    glb = tmp_path / "pano.glb"
    glb.write_bytes(_glb(texture))
    meta = tool.import_pano(glb, tmp_path / "out")
    assert (tmp_path / "out" / "pano.jpg").read_bytes() == texture
    saved = json.loads((tmp_path / "out" / "pano.json").read_text(encoding="utf-8"))
    assert saved == meta
    assert (meta["width"], meta["height"]) == (256, 128)
    assert meta["credit"]["title"] == "Sky Pano - Milkyway" and "MozillaHubs" in meta["credit"]["author"]
    assert "CC-BY-NC-SA-4.0" in meta["credit"]["license"] and meta["credit"]["source"].startswith("https://sketchfab.com/")
    assert "CC BY-NC-SA 4.0" in meta["terms"] and "starmap.jpg" in meta["orientation_note"]
    assert meta["orientation"]["north"] == "up" and meta["orientation"]["ra_direction"] in ("left", "right")


@pytest.mark.parametrize("data, text", [
    (b"not a glb at all, just bytes", "не GLB"),
    (b"glTF" + struct.pack("<II", 1, 12) + b"\0" * 8, "glTF 2.0"),
])
def test_rejects_broken_files(tmp_path, data, text):
    tool = _tool()
    path = tmp_path / "bad.glb"
    path.write_bytes(data)
    with pytest.raises(tool.PanoError, match=text):
        tool.read_glb(path)


def test_rejects_non_equirectangular_and_missing_texture(tmp_path):
    tool = _tool()
    square = tmp_path / "square.glb"
    square.write_bytes(_glb(_jpeg(128, 128)))
    with pytest.raises(tool.PanoError, match="2:1"):
        tool.import_pano(square, tmp_path / "o")
    js, binary = tool.read_glb(square)
    js["images"] = []
    with pytest.raises(tool.PanoError, match="немає вбудованої"):
        tool.extract_texture(js, binary)
    js["images"] = [{"bufferView": 0, "mimeType": "image/webp"}]
    with pytest.raises(tool.PanoError, match="Невідомий тип"):
        tool.extract_texture(js, binary)


def _synthetic_sky(tool, sign: int, center: float, w=512, h=256):
    """Смуга вздовж галактичної площини на рівнопроміжній карті відомої орієнтації; центр Галактики яскравіший."""
    ra, dec, lon = tool.galactic_plane_icrf(1441)
    img = np.full((h, w), 12.0)
    rel = ((ra - center + 180.0) % 360.0) - 180.0
    cols = (((0.5 + sign * rel / 360.0) * w).astype(int)) % w
    rows = np.clip(((0.5 - dec / 180.0) * h).astype(int), 0, h - 1)
    boost = 120.0 + 100.0 * np.cos(np.radians(lon))  # l = 0 — найяскравіше, l = 180 — найтемніше
    for c, r, b in zip(cols, rows, boost, strict=True):
        img[max(0, r - 3):r + 4, max(0, c - 3):c + 4] += b
    from PIL import Image, ImageFilter

    blurred = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(3))
    return np.asarray(blurred, dtype=float)


@pytest.mark.parametrize("sign, center", [(1, 179.5), (-1, 208.0), (1, 40.0), (-1, 300.0)])
def test_fit_orientation_recovers_known_orientation(sign, center):
    tool = _tool()
    fit = tool.fit_orientation(_synthetic_sky(tool, sign, center))
    assert fit["north"] == "up"
    assert fit["ra_direction"] == ("right" if sign > 0 else "left")
    diff = abs(((fit["ra_center_deg"] - center + 180) % 360) - 180)
    assert diff <= 3.0, f"{fit} проти центру {center}"
    assert fit["center_minus_anticenter"] > 0


def test_galactic_plane_geometry():
    """Площина проходить через центр Галактики (RA 266,4°, Dec −28,9°) і досягає |Dec| ≈ 62,9° (90° − 27,13°)."""
    tool = _tool()
    ra, dec, lon = tool.galactic_plane_icrf(721)
    i = int(np.argmin(np.abs(lon - 0)))
    assert abs(ra[i] - 266.405) < 0.1 and abs(dec[i] - (-28.936)) < 0.1
    assert abs(dec.max() - 62.87) < 0.1 and abs(dec.min() + 62.87) < 0.1
