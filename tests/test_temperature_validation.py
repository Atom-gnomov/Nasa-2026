"""Звірка температури LRO Diviner з опублікованими значеннями та з незалежним рельєфом LOLA.

Пропускається, якщо дані не підготовлено (python tools/build_temperature_data.py).
Джерела еталонів:
  Williams et al. (2017), Icarus 283, 300–325 — екватор: полудень ≈ 390 K, перед світанком ≈ 95 K;
  Paige et al. (2010), Science 330, 479–482 — холодні пастки південного полюса: T_max < ~110 K.
"""

from pathlib import Path

import numpy as np
import pytest

TEMP_DIR = Path(__file__).resolve().parents[1] / "data_cache" / "temperature"


@pytest.fixture(scope="module")
def gcp():
    if not (TEMP_DIR / "gcp_tbol.npy").exists():
        pytest.skip("дані Diviner не підготовлено")
    tbol = np.load(TEMP_DIR / "gcp_tbol.npy", mmap_mode="r")
    stats = dict(np.load(TEMP_DIR / "gcp_stats.npz"))
    lat = -90 + (np.arange(tbol.shape[0]) + 0.5) * 180 / tbol.shape[0]
    return tbol, stats, np.abs(lat) < 5


def test_equator_noon_and_predawn_match_williams_2017(gcp):
    tbol, _, eq = gcp
    step = 24 / tbol.shape[2]
    def median_k(h0, h1):
        t = np.asarray(tbol[eq][:, :, int(h0 / step):int(h1 / step)], dtype=float) / 10
        t[t == 0] = np.nan
        return np.nanmedian(t)
    assert median_k(11.75, 12.25) == pytest.approx(390, abs=8)
    assert median_k(5.0, 6.0) == pytest.approx(95, abs=6)


def test_equator_diurnal_range(gcp):
    _, stats, eq = gcp
    assert 380 < np.nanmedian(stats["max_k"][eq]) < 400
    assert 85 < np.nanmedian(stats["min_k"][eq]) < 105


@pytest.fixture(scope="module")
def prp():
    if not (TEMP_DIR / "prp_south.npz").exists():
        pytest.skip("полярний продукт Diviner PRP не підготовлено")
    return dict(np.load(TEMP_DIR / "prp_south.npz"))


def _prp_at(prp, lat, lon, key, half=300_000.0):
    r = 2 * 1_737_400.0 * np.tan(np.radians(90 - abs(lat)) / 2)
    x, y = r * np.sin(np.radians(lon)), r * np.cos(np.radians(lon))
    n = prp[key].shape[0]
    return float(prp[key][int((y + half) / (2 * half) * n), int((x + half) / (2 * half) * n)])


def test_shackleton_floor_is_a_cold_trap_with_surface_ice(prp):
    """Дно Шеклтона: за LOLA сюди не потрапляє Сонце (tests/test_dem_validation.py), за Diviner —
    холодна пастка з T_max < 110 K і стабільним льодом на поверхні. Два незалежні набори даних узгоджені."""
    assert _prp_at(prp, -89.67, 129.78, "max_k") < 110
    assert _prp_at(prp, -89.67, 129.78, "ice_depth_m") == 0.0


def test_ice_stability_follows_temperature(prp):
    """Підповерхневий лід визначає річна СЕРЕДНЯ температура (поріг ~110 K, Paige et al. 2010), а лід
    на самій поверхні — річний МАКСИМУМ: короткий денний прогрів не доходить на глибину кількох сантиметрів."""
    tavg, tmax, ice = prp["avg_k"], prp["max_k"], prp["ice_depth_m"]
    cold, warm = tavg < 110, tavg > 130
    assert cold.sum() > 10_000 and warm.sum() > 10_000
    assert np.mean(np.isfinite(ice[cold])) > 0.995  # нижче ~110 K — лід стабільний у межах 2,87 м
    assert np.mean(np.isfinite(ice[warm])) < 0.01  # вище ~130 K — ні
    surface = ice == 0.0
    assert np.mean(tmax[surface] < 130) > 0.99  # лід просто на поверхні — лише в холодних пастках


def test_prp_is_registered_to_lola_relief():
    """Орієнтація полярного продукту: висоти трикутників PRP (tri_calt) збігаються з LOLA LDEM_80S_80M.

    Дзеркальне чи повернуте розміщення дало б кореляцію ≤ 0,3 і розбіжність у кілометри
    (перевірено: як є — 0,9996 і 28 м; дзеркало — 0,30 і 1,6 км).
    """
    from app.core.dem import open_dem

    src = TEMP_DIR / "src" / "dlre_prp_south.tab"
    lbl = TEMP_DIR.parent / "globe" / "src" / "ldem_80s_80m.lbl"
    if not src.exists() or not lbl.exists():
        pytest.skip("немає вихідного PRP або LDEM_80S_80M")
    lon, lat, alt_km = np.loadtxt(src, delimiter=",", skiprows=1, usecols=(9, 10, 11), max_rows=300_000).T
    dem = open_dem(lbl)
    ok = dem.covers_many(lat, lon)
    h_km = dem(lat[ok], lon[ok]) / 1000.0
    assert np.corrcoef(alt_km[ok], h_km)[0, 1] > 0.99
    assert np.median(np.abs(alt_km[ok] - h_km)) < 0.1
    mirrored = dem(lat[ok], -lon[ok]) / 1000.0
    assert np.corrcoef(alt_km[ok], mirrored)[0, 1] < 0.8
