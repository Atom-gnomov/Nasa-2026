"""GET /api/terrain: сітка висот навколо точки з DEM (поверхня для виду «з поверхні»).

Геометрію перевіряє синтетичний DEM (працює і в CI без даних NASA); справжній LOLA — лише локально.
"""

import base64
from pathlib import Path

import numpy as np
import pytest

from app.services import elevation, terrain
from tests.test_contracts import api_validator, assert_valid

R = terrain.R_MOON_M
DEM_DIR = Path(__file__).resolve().parents[1] / "data_cache" / "globe" / "src"


def _heights(body: dict) -> np.ndarray:
    n = body["n"]
    arr = np.frombuffer(base64.b64decode(body["heights_b64"]), dtype="<f4")
    assert arr.size == n * n
    return arr.reshape(n, n)  # [i (на північ), j (на схід)]


class PlaneDem:
    """Синтетичний DEM: висота = 1000 м на градус широти, 500 м на градус довготи; покриває все."""

    id = "fake_plane"
    resolution_m = 100.0

    def covers(self, lat, lon):
        return True

    def covers_many(self, lat, lon):
        return np.ones(np.shape(lat), dtype=bool)

    def __call__(self, lat, lon):
        return 1000.0 * np.asarray(lat, dtype=float) + 500.0 * np.asarray(lon, dtype=float)


@pytest.fixture
def plane(monkeypatch):
    dem = PlaneDem()
    monkeypatch.setattr(elevation, "available", lambda: (dem,))
    return dem


def test_flat_without_dem_matches_contract(client):
    res = client.get("/api/terrain?lat=0.67416&lon=23.47314")
    assert res.status_code == 200
    body = res.get_json()
    assert_valid(api_validator("TerrainPatch"), body)
    assert body["source"] == "flat" and body["sources"] == [] and body["resolution_m"] == 0.0
    assert body["n"] == 33 and body["radius_km"] == 5.0
    assert not _heights(body).any()


@pytest.mark.parametrize("query", [
    "lat=0&lon=0&n=100",  # парне
    "lat=0&lon=0&n=7",  # менше мінімуму
    "lat=0&lon=0&n=403",  # більше максимуму
    "lat=0&lon=0&n=abc",
    "lat=0&lon=0&radius_km=0.1",
    "lat=0&lon=0&radius_km=101",
    "lat=95&lon=0",
    "lon=0",
])
def test_bad_requests(client, query):
    res = client.get(f"/api/terrain?{query}")
    assert res.status_code == 400, query
    assert res.get_json()["error"] == "bad_request"


def test_defaults_follow_dem_resolution():
    assert terrain.default_radius_km(20) == 5 and terrain.default_radius_km(80) == 10
    assert terrain.default_radius_km(474) == 30 and terrain.default_radius_km(1895) == 60
    for res in (20, 80, 474, 1895, 0):
        radius = terrain.default_radius_km(res)
        n = terrain.default_n(radius, res)
        assert n % 2 == 1 and 33 <= n <= 301, (res, n)
    assert terrain.default_n(5, 20) == 301  # 500 кроків, обмежено 301


def test_orientation_and_values_on_synthetic_dem(client, plane):
    """i росте на північ, j — на схід; висота вузла = DEM у точці, куди сітка його проєктує на сферу."""
    lat0, lon0, radius_km, n = 10.0, 20.0, 10.0, 41
    body = client.get(f"/api/terrain?lat={lat0}&lon={lon0}&radius_km={radius_km}&n={n}").get_json()
    assert_valid(api_validator("TerrainPatch"), body)
    h = _heights(body)
    c = (n - 1) // 2
    assert body["source"] == "fake_plane" and body["sources"] == ["fake_plane"] and body["n"] == n
    assert body["ground_height_m"] == pytest.approx(1000 * lat0 + 500 * lon0, abs=0.1)
    assert h[c, c] == 0.0
    s = 2 * radius_km * 1000 / (n - 1)
    assert body["spacing_m"] == pytest.approx(s, abs=1e-3)

    la0 = np.radians(lat0)
    for k in (-20, -7, 5, 20):  # вузли рівно на північ (k > 0) і на південь від центра
        d = k * s
        lat_new = np.degrees(np.arcsin((R * np.sin(la0) + d * np.cos(la0)) / np.hypot(R, d)))
        assert h[c + k, c] == pytest.approx(1000 * (lat_new - lat0), abs=0.05), k
    for k in (-20, -7, 5, 20):  # вузли на схід (k > 0): широта змінюється лише через кривину, довгота — зростає
        d = k * s
        lat_new = np.degrees(np.arcsin(R * np.sin(la0) / np.hypot(R, d)))
        lon_new = lon0 + np.degrees(np.arctan2(d, R * np.cos(la0) - 0.0))
        expected = 1000 * (lat_new - lat0) + 500 * (lon_new - lon0)
        assert h[c, c + k] == pytest.approx(expected, abs=0.5), k
    assert h[c + 20, c] > 0 > h[c - 20, c], "північ вище"
    assert h[c, c + 20] > 0 > h[c, c - 20], "схід вище (500 м/° довготи)"
    assert body["min_height_m"] == pytest.approx(float(h.min()), abs=0.1)
    assert body["max_height_m"] == pytest.approx(float(h.max()), abs=0.1)


def test_grid_north_at_the_pole_points_to_the_given_meridian():
    """На полюсі «північ» — напрямок на меридіан lon (MATH §5): вузол на північ лежить на цьому меридіані."""
    lat_g, lon_g = terrain._grid_latlon(-90.0, 30.0, 10_000.0, 21)
    c = 10
    assert lat_g[c, c] == pytest.approx(-90.0, abs=1e-6)
    assert lat_g[c + 5, c] > -90.0 and lon_g[c + 5, c] == pytest.approx(30.0, abs=1e-6)
    assert lon_g[c - 5, c] == pytest.approx(-150.0, abs=1e-6), "на південь — протилежний меридіан"
    assert lon_g[c, c + 5] == pytest.approx(120.0, abs=1e-6), "на схід — +90° від меридіана північ"


@pytest.fixture
def real_dem_app():
    from app import create_app
    from app.config import Config

    for name in ("ldem_16", "ldem_875s_20m"):
        if not (DEM_DIR / f"{name}.lbl").exists():
            pytest.skip(f"{name} не завантажено")
    app = create_app(Config)
    app.config["DEM_DIR"] = DEM_DIR
    with app.app_context():
        yield app


def test_shackleton_patch_from_real_lola(real_dem_app):
    """Шеклтон (IAU: −89,67°, 129,78°) — кратер діаметром ≈ 21 км і глибиною кілометри (LOLA, Zuber et al. 2012)."""
    client = real_dem_app.test_client()
    body = client.get("/api/terrain?lat=-89.67&lon=129.78&radius_km=15&n=151").get_json()
    assert_valid(api_validator("TerrainPatch"), body)
    h = _heights(body)
    c = (body["n"] - 1) // 2
    assert body["source"] == "ldem_875s_20m" and body["resolution_m"] == 20.0
    assert h[c, c] == 0.0
    assert body["max_height_m"] - body["min_height_m"] > 3000.0  # вал над дном
    assert body["max_height_m"] > 1000.0, "вал кратера значно вище дна, з якого дивимось"
    assert body["missing_fraction"] == 0.0
    # висота точки збігається з /api/elevation (той самий DEM)
    el = client.get("/api/elevation?lat=-89.67&lon=129.78").get_json()
    assert body["ground_height_m"] == pytest.approx(el["height_m"], abs=0.1)
