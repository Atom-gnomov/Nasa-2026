"""Файли хостингу (I3–I4): Dockerfile, compose, конфіги Fly.io й Render не розходяться із застосунком."""

import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_healthcheck_path_exists_and_is_cheap(client):
    """Усі конфіги питають /api/meta: він має відповідати 200 без важких розрахунків."""
    assert client.get("/api/meta").status_code == 200


def test_dockerfile_runs_the_app_factory_under_gunicorn_with_a_data_volume():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "'app:create_app()'" in text and "gunicorn" in text
    assert "LSE_CACHE_DIR=/data" in text and "VOLUME /data" in text
    assert "USER lse" in text  # не root
    assert "gunicorn" in (ROOT / "requirements-prod.txt").read_text(encoding="utf-8")


def test_compose_mounts_the_data_volume_and_matches_the_dockerfile_port():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    web = compose["services"]["web"]
    assert "8000:8000" in web["ports"]
    assert any(v.endswith(":/data") for v in web["volumes"])
    assert "lse-data" in compose["volumes"]


def test_fly_and_render_configs_agree_with_the_image():
    fly = tomllib.loads((ROOT / "fly.toml").read_text(encoding="utf-8"))
    assert fly["http_service"]["internal_port"] == int(fly["env"]["PORT"]) == 8000
    assert fly["mounts"][0]["destination"] == fly["env"]["LSE_CACHE_DIR"] == "/data"
    assert fly["http_service"]["checks"][0]["path"] == "/api/meta"
    render = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    svc = render["services"][0]
    assert svc["runtime"] == "docker" and svc["healthCheckPath"] == "/api/meta"
    assert svc["disk"]["mountPath"] == "/data"
    assert not any(e.get("value", "").lower().startswith(("sk-", "tok")) for e in svc["envVars"])  # без секретів
