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
])
def test_data_files_match_schemas(data_file, schema_file):
    schema = json.loads((SCHEMAS / schema_file).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert_valid(Draft202012Validator(schema), json.loads((DATA / data_file).read_text(encoding="utf-8")))


def test_ids_are_unique():
    for name in ("sites.json", "dsn_stations.json", "launch_sites.json"):
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
