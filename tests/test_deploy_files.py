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


def _jsonc(path):
    import json
    import re

    text = path.read_text(encoding="utf-8")
    return json.loads(re.sub(r"^\s*//.*$", "", text, flags=re.M))


def test_cloudflare_container_config_matches_worker_and_image():
    cfg = _jsonc(ROOT / "cloudflare" / "wrangler.jsonc")
    worker = (ROOT / "cloudflare" / "src" / "index.js").read_text(encoding="utf-8")
    container = cfg["containers"][0]
    assert container["image"] == "../Dockerfile" and container["image_build_context"] == ".."
    assert f"class {container['class_name']} extends Container" in worker
    binding = cfg["durable_objects"]["bindings"][0]
    assert binding["class_name"] == container["class_name"] and f"env.{binding['name']}" in worker
    assert container["class_name"] in cfg["migrations"][0]["new_sqlite_classes"]
    assert "defaultPort = 8000" in worker  # порт образу (Dockerfile: PORT=8000)
    assert "SECRET_KEY:" not in worker and "TOKEN" not in worker  # секрети — лише через wrangler secret


def test_cloudflare_tunnel_service_is_optional_and_has_no_token_in_file():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    tunnel = compose["services"]["cloudflared"]
    assert tunnel["profiles"] == ["tunnel"]  # без --profile tunnel не стартує
    assert tunnel["environment"]["TUNNEL_TOKEN"].startswith("${TUNNEL_TOKEN")  # значення — з .env
