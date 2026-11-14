"""Графіки таймлайну (app/static/js/charts.js): справжня відповідь /api/timeline через логіку графіка в Node."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

CHARTS_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "js" / "charts.js"
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="Node.js не встановлено")
def test_chart_logic_on_real_timeline(client, tmp_path):
    pytest.importorskip("naif_de440")
    res = client.get("/api/timeline?lat=-89.5&lon=0&start=2027-07-01T00:00Z&end=2027-07-03T00:00Z&step_h=6")
    assert res.status_code == 200
    data = tmp_path / "timeline.json"
    data.write_text(json.dumps(res.get_json()), encoding="utf-8")
    script = (
        f"const c = await import({json.dumps(CHARTS_JS.as_uri())});"
        f"const t = JSON.parse(require('node:fs').readFileSync({json.dumps(str(data))}, 'utf8'));"
        "const s = c.timelineSeries(t); const r = c.elevationRange(s);"
        "console.log(JSON.stringify({ n: s.t.length, range: r, ticks: c.angleTicks(r), dates: c.dateTickIndices(s),"
        " lines: s.t.map((_, i) => c.readout(s, i)), ids: [...new Set(s.comm.flat())] }));"
    )
    proc = subprocess.run(
        [NODE, "--input-type=commonjs", "-e", f"(async () => {{ {script} }})()"],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    body = res.get_json()
    assert out["n"] == len(body["times"]) == 9
    assert out["range"]["min"] <= 0 <= out["range"]["max"]
    assert 0 in out["ticks"]
    assert out["dates"] == [0, 4, 8]  # кожна доба при кроці 6 год
    for line in out["lines"]:
        assert "NaN" not in line and "undefined" not in line, line
    assert set(out["ids"]) <= {s["station_id"] for s in body["stations"]}
