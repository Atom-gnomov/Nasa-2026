"""Звірка з офіційними даними: справжні продукти LOLA (PDS) проти опублікованих NASA/LROC чисел.

Тести пропускаються, якщо DEM не завантажено (python tools/build_globe_textures.py).
Допуски обґрунтовано роздільністю DEM: LDEM_16 — 1,9 км на піксель, полярні — 20–80 м.
"""

from pathlib import Path

import numpy as np
import pytest

from app.core.dem import open_dem

DEM_DIR = Path(__file__).resolve().parents[1] / "data_cache" / "globe" / "src"


def _dem(name: str):
    lbl = DEM_DIR / f"{name}.lbl"
    if not lbl.exists():
        pytest.skip(f"{name} не завантажено")
    dem = open_dem(lbl)
    try:
        _ = dem.data
    except ValueError:
        pytest.skip(f"{name} завантажено не повністю")
    return dem


@pytest.mark.parametrize("name", ["ldem_16", "ldem_64"])
@pytest.mark.parametrize("lat, lon, lroc_height_m, source", [
    # LROC: «Topographic Map of the Chang'e 4 Site» — https://www.lroc.asu.edu/images/1100
    (-45.4561, 177.5885, -5927.0, "Chang'e 4"),
    # LROC: «Chandrayaan-3 Landing Site» — https://www.lroc.asu.edu/images/1314
    (-69.3741, 32.32, 532.0, "Chandrayaan-3"),
])
def test_height_matches_lroc_published(name, lat, lon, lroc_height_m, source):
    """Висота в місцях посадки збігається з опублікованою LROC (обидва посадкові майданчики рівні)."""
    h = float(_dem(name)(lat, lon))
    assert h == pytest.approx(lroc_height_m, abs=25.0), f"{source}: {h:.1f} м проти {lroc_height_m} м (LROC)"


@pytest.mark.parametrize("polar_name", ["ldem_80s_80m", "ldem_875s_20m"])
def test_polar_and_global_products_agree(polar_name):
    """Полярний і глобальний продукти — незалежні сітки LOLA; на перекритті збігаються.

    Це перевіряє формули проєкції: дзеркальне чи повернуте зображення дало б кореляцію ≪ 0,99.
    """
    polar = _dem(polar_name)
    glob = _dem("ldem_16")
    lon = np.linspace(-180, 179.5, 720)
    lats = (-81.0, -84.0, -86.0) if polar.edge_lat == -80 else (-87.7, -88.5, -89.2)
    for lat in lats:
        a = polar(np.full_like(lon, lat), lon)
        b = glob(np.full_like(lon, lat), lon)
        assert np.corrcoef(a, b)[0, 1] > 0.99, lat
        assert np.median(np.abs(a - b)) < 60.0, lat
        mirrored = glob(np.full_like(lon, lat), -lon)
        assert np.corrcoef(a, mirrored)[0, 1] < 0.9, "дзеркальна орієнтація не має збігатися"


@pytest.fixture
def real_dem_app():
    from app import create_app
    from app.config import Config

    _dem("ldem_16")
    _dem("ldem_875s_20m")
    app = create_app(Config)
    app.config["DEM_DIR"] = DEM_DIR
    with app.app_context():
        yield app


def test_shackleton_floor_is_permanently_shadowed(real_dem_app):
    """Дно Шеклтона — область вічної тіні (LRO/LOLA, Mazarico et al. 2011): Сонце не сходить ніколи.

    Гладка сфера тут дала б «Сонце видно» — тест перевіряє, що метрики беруть горизонт з рельєфу.
    """
    pytest.importorskip("naif_de440")
    from datetime import datetime, timezone

    from app.services import horizon, metrics

    assert horizon.mask_source(-89.67, 129.78) == "ldem_875s_20m"
    mask = horizon.load_mask(-89.67, 129.78, 2.0)
    assert mask.elevations_deg.min() > 10.0  # стіни кратера вищі за будь-яке положення Сонця (≤ ~1,6°)
    for month in range(1, 13):
        m = metrics.site_metrics(-89.67, 129.78, datetime(2027, month, 1, 6, tzinfo=timezone.utc), 2.0)
        assert m.sun_visible_fraction == 0.0, month
        assert m.hours_to_sunrise is None  # схід Сонця не знайдено за 30 діб


def test_shackleton_is_a_deep_crater_with_pole_on_rim():
    """IAU: центр Шеклтона −89,67°, 129,78°; полюс лежить на його валу — дно на кілометри нижче."""
    polar = _dem("ldem_80s_80m")
    floor = float(polar(-89.67, 129.78))
    rim_pole = float(polar(-90.0, 0.0))
    assert rim_pole - floor > 3000.0
