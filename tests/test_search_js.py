"""Вкладка «Підбір» (app/static/js/search.js): тіло запиту з форми проходить контракт і справжній /api/search,
а справжня відповідь без помилок перетворюється на рядки таблиці."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_contracts import api_validator, assert_valid

pytest.importorskip("naif_de440")

ROOT = Path(__file__).resolve().parents[1]
SEARCH_JS = ROOT / "app" / "static" / "js" / "search.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js не встановлено")


def run_node(script: str, tmp_path: Path) -> dict:
    code = f"import * as s from {json.dumps(SEARCH_JS.as_uri())}; {script}"
    proc = subprocess.run([NODE, "--input-type=module", "-e", code], capture_output=True, text=True,
                          encoding="utf-8", timeout=60, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@pytest.mark.parametrize("patch", [
    "{}",
    "{ regionKey: 'polar', minSunHours: 100, minCommHours: 50, mode: 'maximin' }",
    "{ regionKey: 'custom', custom: { lat_min: -88, lat_max: -80, grid_step_deg: 4 }, days: 10, heightM: 2 }",
])
def test_form_request_is_valid_and_accepted_by_server(client, tmp_path, patch):
    script = (f"const form = {{ ...structuredClone(s.DEFAULT_FORM), ...{patch} }};"
              "console.log(JSON.stringify(s.buildSearchRequest(form, '2027-07-01T00:00Z')));")
    body = run_node(script, tmp_path)
    assert_valid(api_validator("SearchRequest"), body)
    body["limit"] = 5
    res = client.post("/api/search", json=body)
    assert res.status_code == 200, res.get_json()
    assert_valid(api_validator("SearchResponse"), res.get_json())


def test_real_response_becomes_table_rows(client, tmp_path):
    body = {"start": "2027-01-01T00:00:00Z", "end": "2027-01-08T00:00:00Z", "region": {"lat_min": -90, "lat_max": -85},
            "grid_step_deg": 2.5, "priorities": ["energy", "comms", "radiation"], "min_sun_hours": 120, "limit": 8,
            "include_catalog": True}
    data = client.post("/api/search", json=body).get_json()
    (tmp_path / "r.json").write_text(json.dumps(data), encoding="utf-8")
    script = ("import fs from 'node:fs';"
              "const r = JSON.parse(fs.readFileSync('r.json', 'utf8'));"
              "console.log(JSON.stringify({ rows: s.resultRows(r), note: s.gridNote(r.grid),"
              " cmp: s.describeComparison(r.comparison) }));")
    out = run_node(script, tmp_path)
    assert len(out["rows"]) == len(data["chains"])
    for row in out["rows"]:
        texts = [row["place"], row["sun"], row["comm"], row["station"], *row["violations"]]
        assert all(t and "undefined" not in t and "NaN" not in t for t in texts), row
        assert len(row["factors"]) == 3 and all(0 <= f["value"] <= 1 for f in row["factors"])
    assert "кандидатів" in out["note"] and out["cmp"]


def test_search_lives_on_the_moon_page_under_the_globe(client):
    """Підбір і глобус — на одній сторінці: результати позначаються на карті Місяця."""
    html = client.get("/moon").get_data(as_text=True)
    for marker in ('id="s-run"', 'id="s-priorities"', 'id="s-sun"', 'id="s-comm"', 'data-mode="maximin"',
                   'id="s-advice"', "search.js", 'id="moon-globe"', 'href="/moon#search"'):
        assert marker in html, marker
    assert html.index('id="moon-globe"') < html.index('id="search"')  # карта вище за підбір
    res = client.get("/search")
    assert res.status_code == 302 and res.headers["Location"].endswith("/moon#search")


def test_advice_facts_from_real_search_are_accepted_by_advice_api(client, app, tmp_path, monkeypatch):
    """Факти, які збирає фронтенд зі справжньої відповіді /api/search, проходять контракт і /api/advice."""
    from app.adapters import llm
    from app.services import advice as advice_service

    advice_service.reset_state()
    app.config.update(LLM_BASE_URL="https://llm.example/v1", LLM_MODEL="fake", LLM_API_KEY="k")
    seen = {}

    def fake_chat(cfg, system, user, max_tokens=900):
        seen["user"] = json.loads(user)
        top = seen["user"]["facts"]["top"][0]
        return json.dumps({"summary": f"Найкраща точка набрала {top['score_pct']}.", "tips": [], "caveats": []}), "fake"

    monkeypatch.setattr(llm, "chat", fake_chat)
    body = {"start": "2027-01-01T00:00:00Z", "end": "2027-01-08T00:00:00Z", "region": {"lat_min": -90, "lat_max": -85},
            "grid_step_deg": 2.5, "priorities": ["energy", "comms"], "limit": 8}
    data = client.post("/api/search", json=body).get_json()
    (tmp_path / "r.json").write_text(json.dumps(data), encoding="utf-8")
    script = ("import fs from 'node:fs';"
              "const r = JSON.parse(fs.readFileSync('r.json', 'utf8'));"
              "console.log(JSON.stringify(s.buildAdviceFacts(r, s.DEFAULT_FORM)));")
    facts = run_node(script, tmp_path)
    res = client.post("/api/advice", json={"facts": facts, "language": "uk", "audience": "planner"})
    assert res.status_code == 200, res.get_json()
    assert_valid(api_validator("AdviceResponse"), res.get_json())
    assert res.get_json()["verified"] is True
    assert len(seen["user"]["facts"]["top"]) == 5
    advice_service.reset_state()

