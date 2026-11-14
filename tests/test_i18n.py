"""Мова інтерфейсу (F8): англійський словник app/static/js/i18n/en.json покриває шаблони й не застарів.

Перекладач (i18n.js) і приклади складених рядків перевіряє tests/js/test_i18n.mjs; тут — зв'язок словника з кодом.
"""

import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS_DIR = ROOT / "app" / "static" / "js"


def _tool():
    spec = importlib.util.spec_from_file_location("i18n_missing", ROOT / "tools" / "i18n_missing.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _dictionary() -> dict:
    return json.loads((JS_DIR / "i18n" / "en.json").read_text(encoding="utf-8"))


def test_base_template_is_fully_translated_and_the_rest_almost():
    """base.html (шапка, календар, оверлей метрик) — 100 %; решта шаблонів — не менше 95 %."""
    tool = _tool()
    strings = _dictionary()["strings"]
    per_file = tool.all_template_strings()
    assert per_file["base.html"], "у base.html мають бути українські тексти"
    missing_base = sorted(s for s in per_file["base.html"] if s not in strings)
    assert not missing_base, f"base.html без перекладу (python tools/i18n_missing.py): {missing_base}"
    everything = set().union(*per_file.values())
    missing = sorted(s for s in everything if s not in strings)
    assert len(missing) <= 0.05 * len(everything), f"без перекладу {len(missing)} з {len(everything)}: {missing[:10]}"


def test_dictionary_has_no_stale_keys():
    """Кожен ключ словника ще є в шаблонах або коді: його речення (між {змінними}) мають бути в джерелах."""
    sources = [p.read_text(encoding="utf-8") for p in (ROOT / "app" / "templates").glob("*.html")]
    sources += [p.read_text(encoding="utf-8") for p in JS_DIR.rglob("*.js")]
    text = re.sub(r"\s+", " ", " ".join(sources).replace("\'", "'").replace('\\"', '"'))
    stale = []
    for key in _dictionary()["strings"]:
        # складені повідомлення («A. B.») збираються в коді з окремих речень — перевіряємо кожне
        pieces = re.split(r"\{\w+\}|(?<=\.)\s+", key)
        missing = [q for q in (x.strip().rstrip(".") for x in pieces) if len(q) >= 8 and q not in text]
        if missing:
            stale.append(key)
    assert not stale, f"ключі словника без джерела в коді (видаліть або виправте): {stale}"


def test_language_switch_is_wired_into_every_page(client):
    for path in ("/moon", "/system"):
        html = client.get(path).get_data(as_text=True)
        assert 'data-lang="uk"' in html and 'data-lang="en"' in html, path
        assert "js/i18n.js" in html, path
        assert '<html lang="uk">' in html, "вихідна мова сторінки — українська"


def test_dictionary_is_served_as_static_json(client):
    res = client.get("/static/js/i18n/en.json")
    assert res.status_code == 200
    body = res.get_json()
    assert body["strings"]["Місяць"] == "Moon" and body["phrases"]["год"] == "h"
