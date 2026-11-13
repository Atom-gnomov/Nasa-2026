"""Сервіс температури Diviner: місцевий час, інтерполяція бінів, кодування мап, полярний PRP.

Модульні тести — на маленьких синтетичних сітках (роздільність береться з форми масивів).
Звірка зі справжніми даними й опублікованими значеннями — tests/test_temperature_validation.py.
"""

import base64
import json
import warnings

import numpy as np
import pytest

from app.services import temperature as temp
from tests.test_contracts import api_validator, assert_valid


def test_local_time_convention():
    """Полудень — на довготі підсонячної точки; на схід — пізніше (Сонце на Місяці рухається на захід)."""
    assert temp.local_time_h(30.0, 30.0) == pytest.approx(12.0)
    assert temp.local_time_h(45.0, 30.0) == pytest.approx(13.0)
    assert temp.local_time_h(30.0 + 180.0, 30.0) == pytest.approx(0.0)
    assert temp.local_time_h(-150.0, 30.0) == pytest.approx(0.0)


def test_interp_between_bins_and_gaps():
    step = 6.0  # 4 біни: центри 3, 9, 15, 21 год
    s = np.array([[1000, 2000, 0, 4000]], dtype=np.uint16)
    lt = lambda h: np.array([h])  # noqa: E731
    assert temp._interp_lt(s, lt(6.0), step)[0] == pytest.approx(1500)  # посередині між 3 і 9 год
    assert temp._interp_lt(s, lt(10.0), step)[0] == pytest.approx(2000)  # сусід порожній, найближчий є
    assert temp._interp_lt(s, lt(14.0), step)[0] == 0  # найближчий бін порожній — немає даних
    assert temp._interp_lt(s, lt(0.0), step)[0] == pytest.approx(2500)  # по колу доби: 21 → 3 год


def test_codes_roundtrip():
    v = np.array([20.0, 21.5, 401.0, 500.0, np.nan])
    c = temp._codes(v, temp.T_OFFSET_K, temp.T_SCALE_K)
    assert list(c) == [1, 2, 255, 255, 0]  # вище 401 K — насичення шкали
    decoded = temp.T_OFFSET_K + (c[:3].astype(float) - 1) * temp.T_SCALE_K
    assert np.allclose(decoded, [20.0, 21.5, 401.0])


@pytest.fixture
def synthetic(app, tmp_path):
    """Сітка 10° × 10°, 4 біни місцевого часу: T = 100 + 50 · номер біна (K); комірка (0,0) без даних."""
    n_lat, n_lon, n_lt = 18, 36, 4
    tbol = np.zeros((n_lat, n_lon, n_lt), dtype=np.uint16)
    tbol[:] = (1000 + 500 * np.arange(n_lt)).astype(np.uint16)
    tbol[0, 0] = 0
    np.save(tmp_path / "gcp_tbol.npy", tbol)
    np.save(tmp_path / "gcp_tbol_filled.npy", tbol)
    t = tbol.astype(np.float32) / 10
    t[tbol == 0] = np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # комірка без даних — очікувано порожня
        np.savez(tmp_path / "gcp_stats.npz", max_k=np.nanmax(t, axis=2), min_k=np.nanmin(t, axis=2),
                 mean_k=np.nanmean(t, axis=2), count=(tbol > 0).sum(axis=2))
    n = 40
    prp = {"avg_k": np.full((n, n), 80, np.float32), "max_k": np.full((n, n), 150, np.float32),
           "ice_depth_m": np.full((n, n), np.nan, np.float32)}
    prp["ice_depth_m"][n // 2, n // 2] = 0.0  # біля полюса лід просто на поверхні
    np.savez(tmp_path / "prp_south.npz", **prp)
    meta = {"gcp": {"reference": "synthetic"}, "prp_south": {"half_extent_m": 100_000.0, "cell_m": 5000.0,
                                                             "reference": "synthetic"}}
    (tmp_path / "temperature.json").write_text(json.dumps(meta), encoding="utf-8")
    app.config["TEMP_DIR"] = tmp_path
    return app.test_client()


def test_point_response(synthetic):
    pytest.importorskip("naif_de440")
    res = synthetic.get("/api/temperature?lat=-89.9&lon=10&datetime=2027-07-01T00:00")
    assert res.status_code == 200
    t = res.get_json()
    assert_valid(api_validator("TemperaturePoint"), t)
    assert len(t["diurnal"]) == 4 and t["max_k"] == pytest.approx(250) and t["min_k"] == pytest.approx(100)
    assert t["prp"] is not None and t["prp"]["ice_depth_m"] == 0.0
    nodata = synthetic.get("/api/temperature?lat=-89.9&lon=-179.9&datetime=2027-07-01T00:00").get_json()
    assert nodata["now_k"] is None and nodata["max_k"] is None


@pytest.mark.parametrize("kind", ["now", "max", "min", "mean", "prp_max", "prp_avg", "ice_depth"])
def test_map_response(synthetic, kind):
    pytest.importorskip("naif_de440")
    res = synthetic.get(f"/api/temperature/map?kind={kind}&datetime=2027-07-01T00:00")
    assert res.status_code == 200
    m = res.get_json()
    assert_valid(api_validator("TemperatureMap"), m)
    codes = np.frombuffer(base64.b64decode(m["codes_b64"]), dtype=np.uint8)
    assert codes.size == m["width"] * m["height"]
    if kind in ("max", "min", "mean"):
        assert codes[0] == 0  # комірка без даних
        assert (codes[1:] > 0).all()
    if kind == "ice_depth":
        assert (codes > 0).sum() == 1  # лід на глибині 0 м — це дані, а не «немає даних»


def test_map_rejects_unknown_kind(synthetic):
    assert synthetic.get("/api/temperature/map?kind=bogus").status_code == 400


def test_unavailable_without_data(client):
    res = client.get("/api/temperature?lat=0&lon=0")
    assert res.status_code == 503
    assert_valid(api_validator("Error"), res.get_json())
