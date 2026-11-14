"""Пороги профілів місії (app/data/mission_thresholds.json, задача D5): схема, джерела, значення.

Кожне значення звірено з першоджерелом; цитати в полі quote — дослівні фрагменти документів.
Тест фіксує значення, щоб випадкова правка числа без нового джерела не пройшла непомітно.
"""

import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def _load():
    data = json.loads((ROOT / "app" / "data" / "mission_thresholds.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "contracts" / "schemas" / "mission_thresholds.schema.json").read_text(encoding="utf-8"))
    return data, schema


def test_matches_schema_and_ids_unique():
    data, schema = _load()
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=str)
    assert not errors, [e.message for e in errors]
    ids = [row["id"] for row in data]
    assert len(ids) == len(set(ids))


def test_every_threshold_has_a_source_page_and_quote():
    data, _ = _load()
    for row in data:
        assert row["source"]["url"].startswith("https://"), row["id"]
        assert row["source"]["ref"].strip(), row["id"]
        assert len(row["quote"]) >= 10, row["id"]


def test_values_as_published():
    data, _ = _load()
    got = {row["id"]: (row.get("comparison"), row.get("value"), row.get("unit"), row["kind"]) for row in data}
    assert got == {
        # NASA-STD-3001 Vol. 1 Rev. C: [V1 4030], [V1 4031], табл. 4.8-1
        "crew-career-effective-dose": ("<", 600, "mSv", "requirement"),
        "crew-spe-design-effective-dose": ("<", 250, "mSv", "requirement"),
        "crew-bfo-dose-30-day": ("<=", 250, "mGy-Eq", "requirement"),
        "crew-bfo-dose-1-year": ("<=", 500, "mGy-Eq", "requirement"),
        # Artemis HLS Update 2024, с. 19 «Key Artemis III Landing Requirements»
        "landing-slope-100m": ("<", 10, "deg", "requirement"),
        "eva-slope-2km": ("<", 20, "deg", "requirement"),
        "direct-to-earth-comm": (None, None, None, "requirement"),
        # NASA OIG IG-26-004, с. 30
        "lander-tilt": ("<=", 8, "deg", "requirement"),
        # Artemis HLS Update 2024, с. 23–24 — фільтри аналізу ділянок, не вимоги
        "earth-visibility-screening": (">=", 25, "%", "screening"),
        "sun-visibility-screening": (">=", 5, "%", "screening"),
    }
