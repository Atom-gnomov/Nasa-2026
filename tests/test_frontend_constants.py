"""Сталі, продубльовані у фронтенді, збігаються з app/core/constants.py."""

import re
from pathlib import Path

from app.core.constants import SYNODIC_MONTH_DAYS

JS_DIR = Path(__file__).resolve().parents[1] / "app" / "static" / "js"


def _js_number(filename: str, pattern: str) -> float:
    text = (JS_DIR / filename).read_text(encoding="utf-8")
    match = re.search(pattern, text)
    assert match, f"{filename}: не знайдено {pattern}"
    return float(match.group(1))


def test_calendar_synodic_month_matches_core():
    assert _js_number("calendar.js", r"SYNODIC_MONTH_DAYS = ([\d.]+);") == SYNODIC_MONTH_DAYS


def test_overlay_synodic_month_matches_core():
    assert _js_number("overlay.js", r"SYNODIC_MONTH_H = ([\d.]+) \* 24;") == SYNODIC_MONTH_DAYS
