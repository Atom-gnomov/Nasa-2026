"""Імпортує панораму неба з GLB (Sketchfab «Sky Pano – Milkyway») у data_cache/starmap/ як фон сторінки.

Файл GLB надає користувач (Sketchfab: sky-pano-milkyway-0016725c047a4ea18cd0b5e5ef2fe441);
скрипт нічого не завантажує. Він читає заголовок GLB, дістає вбудовану текстуру (рівнопроміжний JPEG)
і її метадані та калібрує орієнтацію панорами відносно небесних координат ICRF.

⚠️ Ліцензія матеріалу — CC BY-NC-SA 4.0 (автор MozillaHubs): потрібна вказівка авторства (її показує інтерфейс), лише
некомерційне використання, змінені версії поширюються на тих же умовах. Саму панораму в git не додаємо.

Калібрування (оцінка, не астрометрія — панорама стилізована): смуга Чумацького Шляху має лягти на справжню галактичну
площину (її форма в ICRF відома); два можливі напрямки RA розрізняє яскравість: центр Галактики (l ≈ 0°) яскравіший за
антицентр (l ≈ 180°). Результат записується в pano.json: напрям RA, RA центру кадру, оцінки збігу.

Вихід: data_cache/starmap/pano.jpg, pano.json.
Запуск:  python tools/import_sky_pano.py <шлях до sky_pano_-_milkyway.glb>
Залежності лише для цього скрипта: numpy, Pillow.
"""

from __future__ import annotations

import json
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data_cache" / "starmap"

# Галактична система в ICRF (IAU; Hipparcos vol. 1, §1.5.3): північний полюс і напрям на центр Галактики
GAL_POLE_RA_DEG, GAL_POLE_DEC_DEG = 192.85948, 27.12825
GAL_CENTER_RA_DEG, GAL_CENTER_DEC_DEG = 266.40499, -28.93617


class PanoError(ValueError):
    pass


def read_glb(path: Path) -> tuple[dict, bytes]:
    """JSON-чанк і BIN-чанк GLB 2.0."""
    data = Path(path).read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        raise PanoError("Це не GLB (немає заголовка glTF)")
    version, length = struct.unpack("<II", data[4:12])
    if version != 2:
        raise PanoError(f"Підтримується лише glTF 2.0, у файлі {version}")
    js, binary, off = None, b"", 12
    while off + 8 <= len(data):
        size, kind = struct.unpack("<II", data[off:off + 8])
        chunk = data[off + 8:off + 8 + size]
        if kind == 0x4E4F534A:
            js = json.loads(chunk.decode("utf-8"))
        elif kind == 0x004E4942:
            binary = chunk
        off += 8 + size
    if js is None:
        raise PanoError("У GLB немає JSON-чанка")
    return js, binary


def extract_texture(js: dict, binary: bytes) -> tuple[bytes, str]:
    """Перша вбудована текстура: байти й MIME."""
    images = js.get("images") or []
    if not images or "bufferView" not in images[0]:
        raise PanoError("У GLB немає вбудованої текстури")
    view = js["bufferViews"][images[0]["bufferView"]]
    start = view.get("byteOffset", 0)
    raw = binary[start:start + view["byteLength"]]
    mime = images[0].get("mimeType", "")
    if mime not in ("image/jpeg", "image/png"):
        raise PanoError(f"Невідомий тип текстури: {mime or '?'}")
    return raw, mime


def asset_credit(js: dict) -> dict:
    extras = (js.get("asset") or {}).get("extras") or {}
    return {
        "title": extras.get("title", ""), "author": extras.get("author", ""),
        "license": extras.get("license", ""), "source": extras.get("source", ""),
    }


def galactic_plane_icrf(n: int = 721):
    """Точки галактичної площини в ICRF: (RA°, Dec°, довгота l°)."""
    import numpy as np

    ra_p, de_p = np.radians(GAL_POLE_RA_DEG), np.radians(GAL_POLE_DEC_DEG)
    pole = np.array([np.cos(de_p) * np.cos(ra_p), np.cos(de_p) * np.sin(ra_p), np.sin(de_p)])
    ra_c, de_c = np.radians(GAL_CENTER_RA_DEG), np.radians(GAL_CENTER_DEC_DEG)
    center = np.array([np.cos(de_c) * np.cos(ra_c), np.cos(de_c) * np.sin(ra_c), np.sin(de_c)])
    east = np.cross(pole, center)
    lon = np.radians(np.linspace(0, 360, n))
    pts = np.outer(np.cos(lon), center) + np.outer(np.sin(lon), east)
    return (np.degrees(np.arctan2(pts[:, 1], pts[:, 0])) % 360, np.degrees(np.arcsin(pts[:, 2])), np.degrees(lon) % 360)


def fit_orientation(gray, step_deg: float = 0.5, tolerance: float = 0.99) -> dict:
    """Орієнтація рівнопроміжної карти (північ угорі): напрям RA по x і RA центру кадру.

    gray — 2D-масив яскравості (вже розмитий і зменшений). Для кожного кандидата (напрям, RA центру) середня яскравість
    уздовж галактичної площини; серед кандидатів не гірших за tolerance від найкращого вибирається той,
    де центр Галактики яскравіший за антицентр (це знімає дзеркальну неоднозначність: форма площини
    симетрична відносно мінімуму).
    """
    import numpy as np

    h, w = gray.shape
    ra, dec, lon = galactic_plane_icrf()
    near_center = (lon < 50) | (lon > 310)
    near_anti = (lon > 130) & (lon < 230)
    rows = np.clip(((0.5 - dec / 180.0) * h).astype(int), 0, h - 1)
    cands = []
    for sign in (1, -1):  # +1 — RA вправо (атлас), −1 — вліво (вигляд зсередини, як карта NASA SVS)
        for center in np.arange(0.0, 360.0, step_deg):
            rel = ((ra - center + 180.0) % 360.0) - 180.0
            cols = np.clip(((0.5 + sign * rel / 360.0) * w).astype(int) % w, 0, w - 1)
            val = gray[rows, cols]
            asym = float(val[near_center].mean() - val[near_anti].mean())
            cands.append((float(val.mean()), asym, sign, float(center)))
    best_score = max(c[0] for c in cands)
    good = [c for c in cands if c[0] >= tolerance * best_score]
    score, asym, sign, center = max(good, key=lambda c: c[1])
    return {
        "north": "up", "ra_direction": "right" if sign > 0 else "left", "ra_center_deg": round(center, 1),
        "plane_score": round(score, 2), "plane_score_best": round(best_score, 2),
        "center_minus_anticenter": round(asym, 2), "candidates_considered": len(good),
    }


def import_pano(glb_path: Path, out_dir: Path = OUT_DIR) -> dict:
    from io import BytesIO

    import numpy as np
    from PIL import Image, ImageFilter

    js, binary = read_glb(Path(glb_path))
    raw, mime = extract_texture(js, binary)
    img = Image.open(BytesIO(raw)).convert("RGB")
    w, h = img.size
    if abs(w - 2 * h) > 2:
        raise PanoError(f"Очікується рівнопроміжна панорама 2:1, у файлі {w}×{h}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pano.jpg").write_bytes(raw if mime == "image/jpeg" else _to_jpeg(img))
    small = img.convert("L").resize((1024, 512), Image.LANCZOS).filter(ImageFilter.GaussianBlur(6))
    orientation = fit_orientation(np.asarray(small, dtype=float))
    credit = asset_credit(js)
    meta = {
        "file": "pano.jpg", "width": w, "height": h, "projection": "рівнопроміжна, північ угорі",
        "orientation": orientation,
        "orientation_note": "Оцінка за формою галактичної площини й яскравістю центру/антицентру; "
                            "панорама стилізована, "
                            "для астрометрії не придатна (на відміну від starmap.jpg, NASA SVS).",
        "credit": credit,
        "terms": "CC BY-NC-SA 4.0: вказувати авторство; лише некомерційне використання; зміни — на тих же умовах",
        "built": time.strftime("%Y-%m-%d"),
    }
    (out_dir / "pano.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return meta


def _to_jpeg(img) -> bytes:
    from io import BytesIO

    buf = BytesIO()
    img.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    try:
        meta = import_pano(Path(argv[1]))
    except (PanoError, OSError) as err:
        print(f"Помилка: {err}")
        return 1
    o = meta["orientation"]
    print(f"готово: pano.jpg {meta['width']}×{meta['height']}; RA {o['ra_direction']}, центр {o['ra_center_deg']}°; "
          f"{meta['credit'].get('title')} — {meta['credit'].get('author')} ({meta['credit'].get('license', '')[:12]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
