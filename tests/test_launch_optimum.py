"""Оптимальна точка старту (П-12, уточнення користувача): геометрія площини відльоту, критерії «паливо» / «швидкість»,
опції «космодроми» / «будь-яка точка Землі», /api/scene?launch_site=auto."""

import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.core import launch_optimum as lo
from app.core.launch import site_unit_vector
from tests.test_contracts import api_validator, assert_valid

T0 = datetime(2027, 7, 1, tzinfo=timezone.utc)


def _u(dec_deg, ra_deg=0.0):
    d, a = math.radians(dec_deg), math.radians(ra_deg)
    return np.array([math.cos(d) * math.cos(a), math.cos(d) * math.sin(a), math.sin(d)])


# --- геометрія ------------------------------------------------------------------------------------------------


def test_planes_through_moon_direction():
    u = _u(20.0, 35.0)
    assert lo.planes_through(u, 10.0) == []  # нахил менший за |δ| — площини немає
    (single,) = lo.planes_through(u, 20.0)  # найменший нахил — одна площина
    assert lo.inclination_deg(single) == pytest.approx(20.0) and abs(single @ u) < 1e-9
    pair = lo.planes_through(u, 35.0)
    assert len(pair) == 2
    for n in pair:
        assert lo.inclination_deg(n) == pytest.approx(35.0) and abs(n @ u) < 1e-9


def test_rotation_penalty_depends_only_on_inclination():
    assert lo.rotation_penalty_m_s(0.0) == pytest.approx(0.0)
    assert lo.rotation_penalty_m_s(20.0) == pytest.approx(465.1 * (1 - math.cos(math.radians(20.0))))
    assert lo.rotation_penalty_m_s(28.5) > lo.rotation_penalty_m_s(20.0)


def test_plane_through_site_contains_site_and_moon():
    u = _u(18.0, 100.0)
    site = site_unit_vector(28.5, -80.6, T0)
    n = lo.plane_through_site(site, u)
    assert abs(n @ site) < 1e-12 and abs(n @ u) < 1e-12 and n[2] >= 0
    assert lo.inclination_deg(n) >= 28.5 - 1e-9  # площина через майданчик не може мати нахил менший за широту


def test_ground_track_and_node_lie_in_the_plane():
    (n,) = lo.planes_through(_u(20.0, 35.0), 20.0)
    lat, lon = lo.ground_track(n, T0, n=73)
    assert np.abs(lat).max() == pytest.approx(20.0, abs=0.1)  # траса доходить до широти = нахил
    for la, lg in zip(lat[::8], lon[::8], strict=True):
        assert abs(n @ site_unit_vector(float(la), float(lg), T0)) < 1e-9
    node = lo.ascending_node_lon(n, T0)
    assert abs(n @ site_unit_vector(0.0, node, T0)) < 1e-12


def test_earliest_window_waits_for_the_plane():
    u = _u(20.0, 35.0)
    window = lo.earliest_window(5.2, -52.8, lambda t: u, T0, 20.0)
    assert window is not None
    t, n = window
    assert T0 <= t < T0 + timedelta(days=1)
    assert abs(n @ site_unit_vector(5.2, -52.8, t)) < 1e-3
    assert lo.earliest_window(45.9, 63.3, lambda t: u, T0, 20.0) is None  # Байконур не потрапить у площину 20°


# --- сервіс і API -----------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ctx():
    pytest.importorskip("naif_de440")
    from app import create_app
    from app.config import TestConfig

    app = create_app(TestConfig)
    with app.app_context():
        yield app


def _plan(criterion, scope):
    from app.services import launch_optimum as svc

    return svc.plan(T0, criterion, scope)


def test_fuel_spaceports_prefers_the_band_then_the_earliest(ctx):
    res = _plan("fuel", "spaceports")
    best, alts = res["best"], res["alternatives"]
    every = [best, *alts]
    floor = min(o["dv_total_m_s"] for o in every)
    assert best["dv_total_m_s"] <= floor + 5.0
    tied = [o for o in every if o["dv_total_m_s"] <= floor + 5.0]
    assert best["total_h"] == min(o["total_h"] for o in tied)  # серед рівних за паливом — найраніше прибуття
    by_id = {o["site"]["id"]: o for o in every}
    assert by_id["kourou"]["dv_total_m_s"] < by_id["baikonur"]["dv_total_m_s"] - 50  # смуга |φ| ≤ |δ| дешевша
    assert all(o["wait_h"] < 36 for o in every)


def test_speed_spaceports_start_now_with_the_shortest_flight(ctx):
    res = _plan("speed", "spaceports")
    every = [res["best"], *res["alternatives"]]
    assert all(o["wait_h"] == 0 and o["tof_days"] == 3.0 for o in every)
    assert res["best"]["dv_total_m_s"] == min(o["dv_total_m_s"] for o in every)
    fuel_best = _plan("fuel", "spaceports")["best"]
    assert res["best"]["total_h"] < fuel_best["total_h"]  # швидше…
    assert res["best"]["dv_total_m_s"] > fuel_best["dv_total_m_s"]  # …але дорожче за паливом


def test_any_point_is_on_the_equator_and_needs_no_wait(ctx):
    fuel = _plan("fuel", "any")["best"]
    speed = _plan("speed", "any")["best"]
    for o in (fuel, speed):
        assert o["site"]["id"] == "any-point" and o["site"]["lat"] == 0.0 and o["wait_h"] == 0
    spaceport_best = _plan("fuel", "spaceports")["best"]
    assert fuel["dv_total_m_s"] <= spaceport_best["dv_total_m_s"] + 5.0  # не гірше за найкращий космодром
    assert speed["tof_days"] == 3.0 and fuel["tof_days"] >= 3.0


def test_scene_auto_extras_match_contract(ctx):
    client = ctx.test_client()
    for crit, scope in (("fuel", "spaceports"), ("speed", "any")):
        res = client.get(f"/api/scene?datetime=2027-07-01T00:00Z&lat=-85&lon=0&launch_site=auto&markers=0"
                         f"&criterion={crit}&launch_scope={scope}")
        assert res.status_code == 200
        data = res.get_json()
        assert_valid(api_validator("Scene"), data)
        by_kind = {e["kind"]: e for e in data["extras"]}
        assert set(by_kind) == {"rocket", "trajectory", "lander", "ground_track", "launch_choice"}
        choice = by_kind["launch_choice"]
        assert choice["criterion"] == crit and choice["scope"] == scope
        assert by_kind["rocket"]["site_id"] == choice["best"]["site"]["id"]
        assert by_kind["trajectory"]["departure_utc"] == choice["best"]["departure_utc"]
        # ракета стоїть на трасі площини відльоту
        track = np.array(by_kind["ground_track"]["points_latlon"])
        rlat, rlon = by_kind["rocket"]["lat"], by_kind["rocket"]["lon"]
        d = np.hypot(track[:, 0] - rlat, (track[:, 1] - rlon + 180) % 360 - 180)
        assert d.min() < 3.0


def test_scene_auto_rejects_bad_options(ctx):
    client = ctx.test_client()
    for q in ("criterion=cheap", "launch_scope=mars"):
        res = client.get(f"/api/scene?launch_site=auto&markers=0&{q}")
        assert res.status_code == 400
        assert_valid(api_validator("Error"), res.get_json())
