"""Температура в /api/timeline (M11): ряд за місцевим сонячним часом, прапорець `temperature`."""

import numpy as np
import pytest

from app.services import temperature
from tests.test_contracts import api_validator, assert_valid

pytest.importorskip("naif_de440")

def _fake_temp_data(monkeypatch):
    """Синтетична добова крива: 100 K вночі (місцевий час < 6 і ≥ 18), 380 K удень."""
    n_lat, n_lon, n_lt = 180, 360, 96
    lt = (np.arange(n_lt) + 0.5) * 24.0 / n_lt
    curve = np.where((lt >= 6) & (lt < 18), 3800, 1000).astype(np.uint16)
    tbol = np.broadcast_to(curve, (n_lat, n_lon, n_lt))
    fake = temperature.TempData({}, tbol, tbol, {}, None)
    monkeypatch.setattr(temperature, "data", lambda: fake)


def test_timeline_temperature_series_follows_local_time(client, monkeypatch):
    _fake_temp_data(monkeypatch)
    url = "/api/timeline?lat=0&lon=0&start=2027-01-01T00:00:00Z&end=2027-01-31T00:00:00Z&step_h=12&temperature=1"
    res = client.get(url)
    assert res.status_code == 200
    data = res.get_json()
    assert_valid(api_validator("Timeline"), data)
    assert len(data["temperature_k"]) == len(data["times"])
    known = [v for v in data["temperature_k"] if v is not None]
    assert known and min(known) == 100.0 and max(known) == 380.0
    assert data["summary"]["temperature_min_k"] == 100.0 and data["summary"]["temperature_max_k"] == 380.0


def test_timeline_without_temperature_flag_has_no_series(client):
    data = client.get("/api/timeline?lat=0&lon=0&start=2027-01-01T00:00:00Z&end=2027-01-03T00:00:00Z").get_json()
    assert "temperature_k" not in data and "temperature_min_k" not in data["summary"]
