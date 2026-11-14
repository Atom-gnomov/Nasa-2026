"""Вид з поверхні (app/static/js/surface_geometry.js): справжні /api/horizon і /api/timeline через геометрію в Node."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

GEOMETRY_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "js" / "surface_geometry.js"
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="Node.js не встановлено")
def test_geometry_on_real_horizon_and_timeline(client, tmp_path):
    pytest.importorskip("naif_de440")
    mask = client.get("/api/horizon?lat=-89.5&lon=0")
    tl = client.get("/api/timeline?lat=-89.5&lon=0&start=2027-07-01T00:00Z&end=2027-07-03T00:00Z&step_h=6")
    assert mask.status_code == 200 and tl.status_code == 200
    data = tmp_path / "surface.json"
    data.write_text(json.dumps({"mask": mask.get_json(), "tl": tl.get_json()}), encoding="utf-8")
    script = (
        f"const s = await import({json.dumps(GEOMETRY_JS.as_uri())});"
        f"const {{ mask, tl }} = JSON.parse(require('node:fs').readFileSync({json.dumps(str(data))}, 'utf8'));"
        "const p = s.horizonProfile(mask);"
        "const vis = tl.sun.visible_fraction.map((v) => v > 0);"
        "const series = { sun: tl.sun.elevation_deg, earth: tl.earth.elevation_deg };"
        "const back = tl.sun.azimuth_deg.map((az, i) => s.vectorToAzEl(s.skyVector(az, tl.sun.elevation_deg[i])));"
        "console.log(JSON.stringify({ n: p.az.length, closed: p.el[0] === p.el.at(-1),"
        " range: s.panoramaRange(mask, series),"
        " events: vis.map((_, i) => s.eventText('Сонця', vis, i, tl.step_h)),"
        " maxErr: Math.max(...back.map((b, i) => Math.abs(((b.az - tl.sun.azimuth_deg[i] + 540) % 360) - 180))) }));"
    )
    proc = subprocess.run(
        [NODE, "--input-type=commonjs", "-e", f"(async () => {{ {script} }})()"],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    m = mask.get_json()
    assert out["n"] == len(m["elevations_deg"]) + 1 and out["closed"]
    assert out["range"]["min"] <= 0 <= out["range"]["max"]
    assert out["range"]["max"] >= max(m["elevations_deg"])
    assert out["maxErr"] < 1e-6  # азимут → вектор → азимут без втрат
    for text in out["events"]:
        assert "NaN" not in text and "undefined" not in text, text


@pytest.mark.skipif(NODE is None, reason="Node.js не встановлено")
@pytest.mark.parametrize("lat, lon", [(-89.5, 0.0), (0.67416, 23.47314)])
def test_directions_match_scene_enu(client, lat, lon):
    """Напрямок з /api/timeline через skyVector() = sun_enu / earth_enu з /api/scene (схід, північ, зеніт)."""
    pytest.importorskip("naif_de440")
    when = "2027-07-21T00:00Z"
    tl = client.get(f"/api/timeline?lat={lat}&lon={lon}&start={when}&end=2027-07-21T01:00Z&step_h=1").get_json()
    sel = client.get(f"/api/scene?datetime={when}&lat={lat}&lon={lon}&markers=0").get_json()["selected"]
    pairs = [
        (tl["sun"]["azimuth_deg"][0], tl["sun"]["elevation_deg"][0], sel["sun_enu"]),
        (tl["earth"]["azimuth_deg"][0], tl["earth"]["elevation_deg"][0], sel["earth_enu"]),
    ]
    script = (
        f"const s = await import({json.dumps(GEOMETRY_JS.as_uri())});"
        f"console.log(JSON.stringify({json.dumps([[a, e] for a, e, _ in pairs])}.map(([a, e]) => s.skyVector(a, e))));"
    )
    proc = subprocess.run(
        [NODE, "--input-type=commonjs", "-e", f"(async () => {{ {script} }})()"],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    for (x, y, z), (_, _, enu) in zip(json.loads(proc.stdout), pairs, strict=True):
        # сцена: x = схід, y = зеніт, −z = північ
        assert [x, y, -z] == pytest.approx([enu[0], enu[2], enu[1]], abs=2e-3)


TERRAIN_JS = GEOMETRY_JS.with_name("surface_terrain.js")


@pytest.mark.skipif(NODE is None, reason="Node.js не встановлено")
@pytest.mark.parametrize("lat, lon", [(0.67416, 23.47314), (-89.67, 129.78)])
def test_earth_phase_is_complement_of_moon_phase(client, lat, lon):
    """Освітлена частка Землі з місця = 1 − освітлена частка Місяця із Землі (/api/system): та сама кутова
    відстань Сонця від Землі (фазовий кут Місяця); розбіжність — лише паралакс місця на поверхні (≲ 0,3°)."""
    pytest.importorskip("naif_de440")
    query = f"lat={lat}&lon={lon}&start=2027-07-01T00:00Z&end=2027-07-30T00:00Z&step_h=24"  # step_h ≤ 24 за контрактом
    tl = client.get(f"/api/timeline?{query}").get_json()
    script = (
        f"const t = await import({json.dumps(TERRAIN_JS.as_uri())});"
        f"const tl = {json.dumps({'sun': tl['sun'], 'earth': tl['earth']})};"
        "console.log(JSON.stringify(tl.sun.azimuth_deg.map((_, i) => t.earthPhase(tl.sun.azimuth_deg[i],"
        " tl.sun.elevation_deg[i], tl.earth.azimuth_deg[i], tl.earth.elevation_deg[i]).fraction)));"
    )
    proc = subprocess.run(
        [NODE, "--input-type=commonjs", "-e", f"(async () => {{ {script} }})()"],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    earth = json.loads(proc.stdout)
    assert len(earth) == len(tl["times"]) and len(earth) >= 14
    for when, k_earth in zip(tl["times"], earth, strict=True):
        k_moon = client.get(f"/api/system?datetime={when}").get_json()["moon_illumination"]["fraction"]
        assert k_earth == pytest.approx(1.0 - k_moon, abs=0.01), (when, k_earth, k_moon)
    assert max(earth) - min(earth) > 0.8, "за синодичний місяць фаза Землі проходить майже весь діапазон"
