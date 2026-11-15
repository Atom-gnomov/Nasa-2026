"""Справжнє зоряне небо й скляний стиль: маршрут карти, інструмент збирання, відсутність градієнтів, орієнтація карти.

Орієнтацію перевіряємо за справжніми зорями: за формулою starfield.js (0h по центру, RA ліворуч, північ угорі) у
позиціях десяти яскравих зір карти мають бути яскраві точки; для дзеркальних варіантів — ні. Тест пропускається,
якщо карту ще не зібрано (python tools/build_starmap.py) або немає Pillow.
"""

import importlib.util
import re
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app" / "static" / "css"


def _tool():
    spec = importlib.util.spec_from_file_location("build_starmap", ROOT / "tools" / "build_starmap.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_starmap_route_serves_built_map_and_404_without(client, tmp_path, monkeypatch):
    assert client.get("/assets/starmap/starmap.jpg").status_code == 404  # у тестах кеш порожній
    (tmp_path / "starmap").mkdir()
    (tmp_path / "starmap" / "starmap.jpg").write_bytes(b"\xff\xd8\xff test")
    monkeypatch.setitem(client.application.config, "CACHE_DIR", tmp_path)
    res = client.get("/assets/starmap/starmap.jpg")
    assert res.status_code == 200 and res.data.startswith(b"\xff\xd8")


def test_pages_load_the_starfield_and_glass_styles(client):
    for path in ("/moon", "/system", "/mission"):
        html = client.get(path).get_data(as_text=True)
        assert "css/cosmo-glass.css" in html and "js/starfield.js" in html, path
        assert html.index("css/cosmos.css") < html.index("css/cosmo-glass.css"), "скло — після cosmos.css"


def test_glass_stylesheet_has_no_gradients():
    """Вимога: плоске скло — прозорий білуватий фон і розмиття, без градієнтів."""
    css = (CSS / "cosmo-glass.css").read_text(encoding="utf-8")
    assert not re.search(r"(linear|radial|conic)-gradient\s*\(", css)
    assert "backdrop-filter" in css and "rgba(255, 255, 255" in css


def test_tonemap_is_monotonic_and_in_range():
    tool = _tool()
    x = np.array([[[0.0, 0.001, 0.1], [0.5, 1.0, 5.0]]], dtype=np.float32)
    y = tool.tonemap(x)
    assert y.min() >= 0 and y.max() <= 1
    assert y[0, 0, 0] == 0 and y[0, 1, 1] == pytest.approx(1.0, abs=1e-5)
    assert np.all(np.diff(tool.tonemap(np.linspace(0, 2, 50, dtype=np.float32))) >= 0)
    assert tool.tonemap(np.array([-3.0]))[0] == 0  # від'ємний шум не дає артефактів
    assert tool.URL.startswith("https://svs.gsfc.nasa.gov/") and "NASA" in tool.CREDIT and "Gaia" in tool.CREDIT


STARS = [  # J2000 (Hipparcos): назва, RA°, Dec°
    ("Sirius", 101.287, -16.716), ("Canopus", 95.988, -52.696), ("Arcturus", 213.915, 19.182),
    ("Vega", 279.235, 38.784), ("Capella", 79.172, 45.998), ("Rigel", 78.634, -8.202),
    ("Betelgeuse", 88.793, 7.407), ("Altair", 297.696, 8.868), ("Antares", 247.352, -26.432),
    ("Polaris", 37.955, 89.264),
]


def test_starmap_orientation_matches_real_stars():
    image = pytest.importorskip("PIL.Image")
    path = ROOT / "data_cache" / "starmap" / "starmap.jpg"
    if not path.exists():
        pytest.skip("карту не зібрано: python tools/build_starmap.py")
    im = np.asarray(image.open(path).convert("L"), dtype=float)
    h, w = im.shape

    def bright(ra, dec, flip_ra=False, flip_dec=False):
        r = ra - 360 if ra > 180 else ra
        u = 0.5 + r / 360 if flip_ra else 0.5 - r / 360
        v = 0.5 + dec / 180 if flip_dec else 0.5 - dec / 180
        x, y = int(u * w) % w, min(h - 1, max(0, int(v * h)))
        return im[max(0, y - 4):y + 5, max(0, x - 4):x + 5].max() > 120

    assert sum(bright(ra, dec) for _, ra, dec in STARS) == len(STARS)
    assert sum(bright(ra, dec, flip_ra=True) for _, ra, dec in STARS) <= 4
    assert sum(bright(ra, dec, flip_dec=True) for _, ra, dec in STARS) <= 3
