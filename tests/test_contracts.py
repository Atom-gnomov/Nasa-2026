"""Контрактні тести: відповіді API й файли даних відповідають contracts/.

Якщо тест падає — або виправити код, або (свідомо) оновити контракт і docs/CONTRACTS.md.
"""

import json
from pathlib import Path

import numpy as np
import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent
OPENAPI = yaml.safe_load((ROOT / "contracts" / "openapi.yaml").read_text(encoding="utf-8"))
SCHEMAS = ROOT / "contracts" / "schemas"
DATA = ROOT / "app" / "data"


def api_validator(name: str) -> Draft202012Validator:
    """Валідатор для components.schemas.<name> з openapi.yaml (посилання $ref розв'язуються)."""
    root = {"$ref": f"#/components/schemas/{name}", "components": OPENAPI["components"]}
    return Draft202012Validator(root, format_checker=FormatChecker())


def assert_valid(validator: Draft202012Validator, instance):
    errors = sorted(validator.iter_errors(instance), key=str)
    assert not errors, "\n".join(f"{list(e.path)}: {e.message}" for e in errors)


def test_openapi_is_valid_31():
    assert OPENAPI["openapi"].startswith("3.1")
    for path, ops in OPENAPI["paths"].items():
        for method, op in ops.items():
            assert op.get("x-status") in {"implemented", "planned"}, f"{method.upper()} {path}: немає x-status"


def test_all_contract_paths_are_routed(client):
    """Кожна операція з контракту існує на сервері (planned → 501 у форматі Error)."""
    err = api_validator("Error")
    for path, ops in OPENAPI["paths"].items():
        if "{" in path:
            continue
        for method, op in ops.items():
            res = client.open(f"/api{path}", method=method.upper(), json={} if method == "post" else None)
            assert res.status_code != 404 or path == "/sites/{site_id}", f"{method.upper()} {path} не знайдено"
            if op["x-status"] == "planned":
                assert res.status_code == 501, f"{path}: очікується 501"
                assert_valid(err, res.get_json())


@pytest.mark.parametrize("data_file, schema_file", [
    ("sites.json", "sites.schema.json"),
    ("dsn_stations.json", "dsn_stations.schema.json"),
    ("launch_sites.json", "launch_sites.schema.json"),
    ("data_packs.json", "data_packs.schema.json"),
    ("rockets.json", "rockets.schema.json"),
])
def test_data_files_match_schemas(data_file, schema_file):
    schema = json.loads((SCHEMAS / schema_file).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert_valid(Draft202012Validator(schema), json.loads((DATA / data_file).read_text(encoding="utf-8")))


def test_ids_are_unique():
    for name in ("sites.json", "dsn_stations.json", "launch_sites.json", "rockets.json"):
        ids = [r["id"] for r in json.loads((DATA / name).read_text(encoding="utf-8"))]
        assert len(ids) == len(set(ids)), name


def test_other_schemas_are_valid():
    for name in ("horizon_mask.schema.json", "dataset_manifest.schema.json"):
        Draft202012Validator.check_schema(json.loads((SCHEMAS / name).read_text(encoding="utf-8")))


def test_catalog_responses(client):
    for path, schema in (("/api/sites", "Site"), ("/api/dsn", "DsnStation"), ("/api/launch-sites", "LaunchSite")):
        v = api_validator(schema)
        for item in client.get(path).get_json():
            assert_valid(v, item)
    assert_valid(api_validator("Site"), client.get("/api/sites/apollo-11").get_json())
    assert_valid(api_validator("Health"), client.get("/api/health").get_json())


def test_error_responses(client):
    v = api_validator("Error")
    for path, code in (("/api/metrics?lat=100&lon=0", 400), ("/api/sites/nope", 404),
                       ("/api/compare?site=apollo-11", 400), ("/api/unknown", 404)):
        res = client.get(path)
        assert res.status_code == code, path
        assert_valid(v, res.get_json())


def test_metrics_and_compare_responses(client):
    pytest.importorskip("naif_de440")
    m = client.get("/api/metrics?lat=-89.5&lon=350&datetime=2027-07-01T00:00&height=2").get_json()
    assert_valid(api_validator("SiteMetrics"), m)
    assert m["lon"] == pytest.approx(-10.0)
    assert m["datetime"] == "2027-07-01T00:00:00Z"
    v = api_validator("CompareItem")
    for item in client.get("/api/compare?site=apollo-11&site=south-pole&datetime=2027-07-01T00:00").get_json():
        assert_valid(v, item)


def test_system_response(client):
    pytest.importorskip("naif_de440")
    s = client.get("/api/system?datetime=2027-07-01T00:00").get_json()
    assert_valid(api_validator("SystemState"), s)
    m = np.array(s["moon_orientation"])
    assert np.allclose(m @ m.T, np.eye(3), atol=1e-6)  # поворот
    # Відстань Земля–Місяць 356–407 тис. км, Земля над Місяцем — біля центру видимого диска (лібрація ≤ ~8°)
    assert 356_000 < np.linalg.norm(s["moon_km"]) < 407_000
    assert abs(s["sub_earth_point"]["lat"]) < 8 and abs(s["sub_earth_point"]["lon"]) < 9
    # Підсонячна широта на Місяці не виходить за ±1,6° (нахил екватора Місяця до екліптики 1,54°)
    assert abs(s["sub_solar_point"]["lat"]) < 1.6


@pytest.mark.parametrize("dt, sun, earth", [
    # JPL Horizons (DE441, MOON_ME), COMMAND=301 CENTER=500@399 QUANTITIES=14,15, запит 2026-11-13
    ("2027-07-01T00:00", (216.778728, 0.868794), (353.623808, -6.553765)),
    ("2030-01-15T12:00", (45.492768, 0.785346), (358.111765, -2.029675)),
])
def test_system_matches_jpl_horizons(client, dt, sun, earth):
    """Підсонячна й підземна точки збігаються з JPL Horizons у межах точності моделі IAU (~0,01°)."""
    pytest.importorskip("naif_de440")
    s = client.get(f"/api/system?datetime={dt}").get_json()
    for got, (lon, lat) in ((s["sub_solar_point"], sun), (s["sub_earth_point"], earth)):
        assert got["lat"] == pytest.approx(lat, abs=0.02)
        assert (got["lon"] - lon + 180) % 360 - 180 == pytest.approx(0, abs=0.02)


def _geocentric_lat(planetodetic_deg: float) -> float:
    """Horizons дає геодезичну широту перетину лінії «центр Землі → тіло» з еліпсоїдом (ITRF93).
    Ми даємо точку, де тіло в зеніті; для далекого тіла її широта = геоцентрична широта напрямку."""
    f = 1 / 298.257223563
    return float(np.degrees(np.arctan((1 - f) ** 2 * np.tan(np.radians(planetodetic_deg)))))


@pytest.mark.parametrize("dt, sun, moon, illum_pct, phase_deg", [
    # JPL Horizons, запит 2026-11-13: COMMAND=399 CENTER=500@301 QUANTITIES=14,15 (ITRF93);
    # COMMAND=301 CENTER=500@399 QUANTITIES=10,24
    ("2027-07-01T00:00", (180.944626, 23.273049), (133.430892, 24.274869), 13.68065, 136.5803),
    ("2030-01-15T12:00", (2.360775, -21.187781), (130.801712, 23.307107), 83.80731, 47.4529),
])
def test_earth_and_phase_match_jpl_horizons(client, dt, sun, moon, illum_pct, phase_deg):
    """Орієнтація Землі (підсонячна й підмісячна точки) і фаза Місяця збігаються з JPL Horizons."""
    pytest.importorskip("naif_de440")
    s = client.get(f"/api/system?datetime={dt}").get_json()
    m = np.array(s["earth_orientation"])
    assert np.allclose(m @ m.T, np.eye(3), atol=1e-6)
    for got, (lon, lat) in ((s["earth_sub_solar_point"], sun), (s["earth_sub_lunar_point"], moon)):
        assert (got["lon"] - lon + 180) % 360 - 180 == pytest.approx(0, abs=0.02)
        assert got["lat"] == pytest.approx(_geocentric_lat(lat), abs=0.02)
    assert s["moon_illumination"]["fraction"] == pytest.approx(illum_pct / 100, abs=5e-4)
    assert s["moon_illumination"]["phase_angle_deg"] == pytest.approx(phase_deg, abs=0.02)


def test_system_rotations_are_consistent(client):
    """3D-вид повертає тіла матрицями з /api/system: точки «тіло в зеніті» мають дивитися на тіло.

    Перевіряє узгодженість earth_orientation / moon_orientation з векторами положень — саме це
    робить system_view.js (поворот тіло → ICRF = транспонована матриця).
    """
    pytest.importorskip("naif_de440")

    def unit(p):
        lat, lon = np.radians(p["lat"]), np.radians(p["lon"])
        return np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])

    def angle(a, b):
        return np.degrees(np.arccos(np.clip(np.dot(a, b) / np.linalg.norm(a) / np.linalg.norm(b), -1, 1)))

    s = client.get("/api/system?datetime=2027-07-01T00:00").get_json()
    re, rm = np.array(s["earth_orientation"]), np.array(s["moon_orientation"])
    sun, moon = np.array(s["sun_km"]), np.array(s["moon_km"])
    assert angle(re.T @ unit(s["earth_sub_solar_point"]), sun) < 0.02
    assert angle(re.T @ unit(s["earth_sub_lunar_point"]), moon) < 0.02
    assert angle(rm.T @ unit(s["sub_solar_point"]), sun - moon) < 0.01
    assert angle(rm.T @ unit(s["sub_earth_point"]), -moon) < 0.01


def test_orbits_match_reference_values(client):
    """Оскулюючі орбіти: формат, замкненість і відомі значення.

    Земля (барицентр З–М): a ≈ 1 а.о., e ≈ 0,0167, нахил до екліптики J2000 ≈ 0 (JPL, середні
    елементи J2000: a = 1,00000261 а.о., e = 0,01671123). Місяць: a ≈ 384 400 км, нахил 5,14° ± 0,15°
    (коливання), сидеричний місяць 27,32 д; оскулюючі елементи коливаються навколо середніх.
    """
    pytest.importorskip("naif_de440")
    o = client.get("/api/orbits?datetime=2027-07-01T00:00").get_json()
    assert_valid(api_validator("Orbits"), o)
    s = client.get("/api/system?datetime=2027-07-01T00:00").get_json()

    earth = o["earth"]["elements"]
    assert earth["a_km"] / 149_597_870.7 == pytest.approx(1.0, abs=2e-4)
    assert earth["e"] == pytest.approx(0.0167, abs=5e-4)
    assert earth["inclination_deg"] < 0.01
    assert earth["period_days"] == pytest.approx(365.25, abs=0.1)
    assert o["earth"]["max_deviation_km"] < 20_000  # 0,013 % від 1 а.о. за рік

    moon = o["moon"]["elements"]
    assert moon["a_km"] == pytest.approx(384_400, rel=0.02)
    assert 4.9 < moon["inclination_deg"] < 5.4
    assert moon["period_days"] == pytest.approx(27.32, abs=0.3)
    assert o["moon"]["max_deviation_km"] < 0.04 * moon["a_km"]  # збурення від Сонця — до кількох %

    # Еліпс проходить через поточне положення Місяця (найближча з 720 точок — у межах кроку дуги)
    pts = np.array(o["moon"]["points_km"])
    gap = np.min(np.linalg.norm(pts - np.array(s["moon_km"]), axis=1))
    assert gap < 2 * np.pi * moon["apoapsis_km"] / len(pts)


def test_horizon_response(client):
    """Без DEM (модульні тести) — гладка сфера: небо відкрите повністю, доза = відкрита поверхня Chang'e 4."""
    h = client.get("/api/horizon?lat=0.67416&lon=23.47314").get_json()
    assert_valid(api_validator("HorizonMask"), h)
    assert h["source"] == "flat"
    assert h["sky_view_fraction"] == pytest.approx(1.0, abs=1e-6)
    assert h["gcr_dose_usv_per_day"] == pytest.approx(1369.0, abs=0.5)


def test_timeline_apollo_11_synodic_month(client):
    """Apollo 11 (екватор, видимий бік) за два синодичні місяці: Сонце ~½ часу, ціла ніч ~14,8 доби,
    Земля завжди над горизонтом, хоча б одна станція DSN — ~98 % часу (docs/MATH.md, §9.2).
    Вікно у два місяці — щоб найдовша ніч не була розрізана межею періоду."""
    pytest.importorskip("naif_de440")
    t = client.get("/api/timeline?lat=0.67416&lon=23.47314&start=2027-07-01T00:00&end=2027-08-29T01:28"
                   "&step_h=1").get_json()
    assert_valid(api_validator("Timeline"), t)
    s = t["summary"]
    assert len(t["times"]) == len(t["sun"]["elevation_deg"]) == len(t["stations"][0]["available"])
    assert s["sun_fraction"] == pytest.approx(0.5, abs=0.03)
    assert s["longest_night_h"] == pytest.approx(14.77 * 24, abs=12)
    assert s["earth_fraction"] == 1.0
    assert 0.9 < s["comm_fraction"] < 1.0
    assert 0 < s["energy_wh_per_m2"] < 0.30 * 1420 * s["sun_hours"]  # не більше за повний потік


def test_timeline_validation(client):
    assert client.get("/api/timeline?lat=0&lon=0&start=2027-01-02T00:00&end=2027-01-01T00:00").status_code == 400
    assert client.get("/api/timeline?lat=0&lon=0").status_code == 400


def test_elevation_slope_and_aspect(app, tmp_path):
    """Синтетичний DEM: висота росте на схід на 40 м за піксель 1° → схил «дивиться» на захід (270°)."""
    from tests.test_core_dem import CYL_LABEL

    data = np.tile(np.arange(360) * 80, (180, 1))  # DN · 0,5 м = 40 м на піксель
    (tmp_path / "ldem_1.lbl").write_text(
        CYL_LABEL.format(lines=180, samples=360, ppd=1, loff=89.5, soff=179.5), encoding="latin-1")
    data.astype("<i2").tofile(tmp_path / "ldem_1.img")
    app.config["DEM_DIR"] = tmp_path
    e = app.test_client().get("/api/elevation?lat=0&lon=10.5").get_json()
    expected = np.degrees(np.arctan(40.0 / (2 * np.pi * 1_737_400 / 360)))  # 40 м на ~30,3 км ≈ 0,076°
    assert e["slope_deg"] == pytest.approx(expected, abs=0.006)
    assert e["aspect_deg"] == pytest.approx(270.0, abs=0.5)


def test_elevation_response(app, tmp_path):
    """Сервіс висот на синтетичному глобальному DEM: формат відповіді й вибір джерела."""
    from tests.test_core_dem import CYL_LABEL

    data = np.tile(np.arange(360) * 2, (180, 1))
    (tmp_path / "ldem_1.lbl").write_text(
        CYL_LABEL.format(lines=180, samples=360, ppd=1, loff=89.5, soff=179.5), encoding="latin-1")
    data.astype("<i2").tofile(tmp_path / "ldem_1.img")
    app.config["DEM_DIR"] = tmp_path
    res = app.test_client().get("/api/elevation?lat=0&lon=10.5")
    assert res.status_code == 200
    body = res.get_json()
    assert_valid(api_validator("Elevation"), body)
    assert body["height_m"] == pytest.approx(10.0)
    assert body["source"]["id"] == "ldem_1"


def test_elevation_unavailable_without_dem(app, tmp_path):
    app.config["DEM_DIR"] = tmp_path
    res = app.test_client().get("/api/elevation?lat=0&lon=0")
    assert res.status_code == 503
    assert_valid(api_validator("Error"), res.get_json())


def test_planned_schemas_accept_examples():
    """Приклади з docs/CONTRACTS.md для запланованих операцій проходять схеми — фронтенд може на них покладатися."""
    examples = json.loads((ROOT / "contracts" / "examples.json").read_text(encoding="utf-8"))
    for schema_name, instance in examples.items():
        assert_valid(api_validator(schema_name), instance)
