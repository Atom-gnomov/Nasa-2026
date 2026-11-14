"""Бекенд 3D-моделей: /api/models (маніфест) і /api/scene (опис сцени)."""

import numpy as np
import pytest

from tests.test_contracts import api_validator, assert_valid

pytest.importorskip("naif_de440")

WHEN = "2027-07-01T00:00Z"


def norm(v):
    return float(np.linalg.norm(v))


def test_models_manifest_without_assets(client):
    res = client.get("/api/models")
    assert res.status_code == 200
    data = res.get_json()
    assert_valid(api_validator("ModelsManifest"), data)
    assert [b["id"] for b in data["bodies"]] == ["sun", "earth", "moon"]
    assert data["all_available"] is False and len(data["missing"]) == 5
    assert set(data["build_commands"]) == {
        "python tools/build_system_assets.py", "python tools/build_globe_textures.py"}
    assert all(not b["complete"] and b["fallback"]["kind"] == "sphere" for b in data["bodies"])


def test_models_manifest_sees_files_in_cache(client, app, tmp_path):
    (tmp_path / "system").mkdir()
    (tmp_path / "globe").mkdir()
    (tmp_path / "system" / "sun.glb").write_bytes(b"glTF")
    (tmp_path / "system" / "earth.jpg").write_bytes(b"jpg")
    for name in ("color.jpg", "height.bin", "slope.webp"):
        (tmp_path / "globe" / name).write_bytes(b"x" * 10)
    app.config["CACHE_DIR"] = tmp_path
    data = client.get("/api/models").get_json()
    assert_valid(api_validator("ModelsManifest"), data)
    assert data["all_available"] is True and data["missing"] == [] and data["build_commands"] == []
    sun = next(b for b in data["bodies"] if b["id"] == "sun")
    assert sun["complete"] and sun["assets"][0]["size_bytes"] == 4
    assert sun["assets"][0]["url"] == "/assets/system/sun.glb"


def test_scene_matches_contract_and_system_endpoint(client):
    res = client.get(f"/api/scene?datetime={WHEN}")
    assert res.status_code == 200
    scene = res.get_json()
    assert_valid(api_validator("Scene"), scene)
    system = client.get(f"/api/system?datetime={WHEN}").get_json()
    bodies = {b["id"]: b for b in scene["bodies"]}
    assert bodies["moon"]["position_km"] == system["moon_km"]
    assert bodies["sun"]["position_km"] == system["sun_km"]
    assert bodies["earth"]["position_km"] == [0.0, 0.0, 0.0]
    assert bodies["moon"]["orientation"] == system["moon_orientation"]
    assert bodies["earth"]["orientation"] == system["earth_orientation"]
    assert scene["sub_solar_point"] == system["sub_solar_point"] and scene["extras"] == []
    assert scene["selected"] is None


def test_scene_geometry_is_consistent(client):
    scene = client.get(f"/api/scene?datetime={WHEN}").get_json()
    bodies = {b["id"]: b for b in scene["bodies"]}
    assert norm(scene["light"]["direction_icrf"]) == pytest.approx(1.0, abs=1e-5)
    for body in ("earth", "moon"):
        m = np.array(bodies[body]["orientation"])
        assert m @ m.T == pytest.approx(np.eye(3), abs=1e-6)
        assert bodies[body]["unit_to_sun"] and norm(bodies[body]["unit_to_sun"]) == pytest.approx(1.0, abs=1e-5)
    # Земля й Місяць світяться з майже однакового напрямку (Сонце далеко)
    assert np.dot(bodies["earth"]["unit_to_sun"], bodies["moon"]["unit_to_sun"]) > 0.9999
    assert bodies["sun"]["orientation"] is None and bodies["sun"]["unit_to_sun"] is None
    assert [b["radius_km"] for b in scene["bodies"]] == [695700.0, 6378.137, 1737.4]
    assert bodies["earth"]["flattening"] == pytest.approx(1 / 298.257223563)


def test_markers_are_unit_vectors_in_body_frames(client):
    scene = client.get(f"/api/scene?datetime={WHEN}").get_json()
    earth, moon = scene["markers"]["earth"], scene["markers"]["moon"]
    assert {m["id"] for m in earth} == {"goldstone", "madrid", "canberra"}
    assert all(norm(m["unit_itrs"]) == pytest.approx(1.0, abs=1e-5) for m in earth)
    assert all(norm(m["unit_me"]) == pytest.approx(1.0, abs=1e-5) for m in moon)
    pole = next(m for m in moon if m["id"] == "south-pole")
    assert pole["unit_me"] == pytest.approx([0.0, 0.0, -1.0], abs=1e-6)
    goldstone = next(m for m in earth if m["id"] == "goldstone")
    assert goldstone["unit_itrs"][2] > 0.5 and goldstone["unit_itrs"][0] < 0  # північна півкуля, захід від Гринвіча
    canberra = next(m for m in earth if m["id"] == "canberra")
    assert canberra["unit_itrs"][2] < -0.5  # південна півкуля
    assert client.get(f"/api/scene?datetime={WHEN}&markers=0").get_json()["markers"] == {"earth": [], "moon": []}


def test_selected_point_agrees_with_metrics(client):
    scene = client.get(f"/api/scene?datetime={WHEN}&lat=-89.5&lon=0").get_json()
    assert_valid(api_validator("Scene"), scene)
    sel = scene["selected"]
    metrics = client.get(f"/api/metrics?datetime={WHEN}&lat=-89.5&lon=0").get_json()
    assert sel["sun_elevation_deg"] == pytest.approx(metrics["sun_elevation_deg"], abs=0.01)
    assert sel["earth_elevation_deg"] == pytest.approx(metrics["earth_elevation_deg"], abs=0.01)
    assert sel["sun_azimuth_deg"] == pytest.approx(metrics["sun_azimuth_deg"], abs=0.1)
    # зеніт у системі (схід, північ, зеніт) — третя компонента = sin(кут місця)
    assert sel["sun_enu"][2] == pytest.approx(np.sin(np.radians(sel["sun_elevation_deg"])), abs=1e-4)
    assert sel["earth_enu"][2] == pytest.approx(np.sin(np.radians(sel["earth_elevation_deg"])), abs=1e-4)
    assert norm(sel["sun_direction_me"]) == pytest.approx(1.0, abs=1e-5)


@pytest.mark.parametrize("query", [
    "lat=10", "lon=10", "lat=99&lon=0", "lat=0&lon=999", "lat=x&lon=0", "datetime=не-дата"])
def test_scene_validation(client, query):
    res = client.get(f"/api/scene?{query}")
    assert res.status_code == 400
    assert_valid(api_validator("Error"), res.get_json())


# ---------- Політ (G9, П-5) ----------
def test_scene_flight_extras(client):
    pytest.importorskip("naif_de440")
    res = client.get("/api/scene?datetime=2027-07-01T00:00Z&lat=-85&lon=0&launch_site=kourou&markers=0")
    assert res.status_code == 200
    data = res.get_json()
    assert_valid(api_validator("Scene"), data)
    by_kind = {e["kind"]: e for e in data["extras"]}
    assert set(by_kind) == {"rocket", "trajectory", "lander"}
    t = by_kind["trajectory"]
    assert t["departure_utc"] == "2027-07-01T00:00:00Z" and 3.0 <= t["tof_days"] <= 5.0
    assert 3100 < t["dv_tli_m_s"] < 3200 and t["windows_per_day"] == 2
    first, last = t["points_km"][0], t["points_km"][-1]
    assert 6500 < sum(c * c for c in first) ** 0.5 < 6600  # паркувальна орбіта 185 км
    assert sum((a - b) ** 2 for a, b in zip(last, t["moon_at_arrival_km"], strict=True)) ** 0.5 < 1.0
    assert by_kind["rocket"]["site_id"] == "kourou" and by_kind["lander"]["lat"] == -85


def test_scene_flight_without_point_has_no_lander_and_unknown_site_is_404(client):
    pytest.importorskip("naif_de440")
    data = client.get("/api/scene?datetime=2027-07-01T00:00Z&launch_site=cape-canaveral&markers=0").get_json()
    assert {e["kind"] for e in data["extras"]} == {"rocket", "trajectory"}
    assert client.get("/api/scene?markers=0").get_json()["extras"] == []
    res = client.get("/api/scene?launch_site=nope&markers=0")
    assert res.status_code == 404
    assert_valid(api_validator("Error"), res.get_json())


def test_system_page_has_flight_control(client):
    html = client.get("/system/earth-moon").get_data(as_text=True)
    assert 'id="system-flight"' in html and 'data-fact="flight"' in html
