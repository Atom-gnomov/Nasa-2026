"""Порівняння місць (app/static/js/compare.js): поля зі схеми SiteMetrics і справжня відповідь /api/compare."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPARE_JS = ROOT / "app" / "static" / "js" / "compare.js"
NODE = shutil.which("node")


def _schema(name: str) -> dict:
    spec = yaml.safe_load((ROOT / "contracts" / "openapi.yaml").read_text(encoding="utf-8"))
    return spec["components"]["schemas"][name]


def test_compare_js_uses_only_contract_fields():
    """Кожне m.<поле> і s.<поле> у compare.js є в SiteMetrics / CompareItem / stations (захист від одруківок)."""
    text = COMPARE_JS.read_text(encoding="utf-8")
    schema = _schema("SiteMetrics")["properties"]
    station = schema["stations"]["items"]["properties"]
    allowed = set(schema) | set(_schema("CompareItem")["properties"])
    used_metrics = set(re.findall(r"\b(?:m|a|b)\.([a-z_0-9]+)", text))
    used_station = set(re.findall(r"\bs\.([a-z_0-9]+)", text))
    assert {"panel_power_vertical_w_m2", "hours_to_sunset"} <= used_metrics, "регулярний вираз не бачить полів"
    assert used_metrics <= allowed, sorted(used_metrics - allowed)
    assert used_station <= set(station), sorted(used_station - set(station))


@pytest.mark.skipif(NODE is None, reason="Node.js не встановлено")
def test_compare_table_on_real_response(client, tmp_path):
    """Справжня відповідь /api/compare проходить через логіку таблиці compare.js без «undefined»/«NaN»."""
    pytest.importorskip("naif_de440")
    res = client.get("/api/compare?site=apollo-11&site=south-pole&datetime=2027-07-01T00:00")
    assert res.status_code == 200
    data = tmp_path / "compare.json"
    data.write_text(json.dumps(res.get_json()), encoding="utf-8")
    script = (
        f"const {{ tableRows, ROWS }} = await import({json.dumps(COMPARE_JS.as_uri())});"
        f"const [a, b] = JSON.parse(require('node:fs').readFileSync({json.dumps(str(data))}, 'utf8'));"
        "console.log(JSON.stringify({ rows: tableRows(a.metrics, b.metrics), n: ROWS.length }));"
    )
    proc = subprocess.run(
        [NODE, "--input-type=commonjs", "-e", f"(async () => {{ {script} }})()"],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert len(out["rows"]) == out["n"]
    for row in out["rows"]:
        for value in (row["a"], row["b"]):
            assert value and "undefined" not in value and "NaN" not in value, row
        assert row["better"] in ("a", "b", None)
