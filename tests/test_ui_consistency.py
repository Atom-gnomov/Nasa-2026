"""Єдина шкала інтерфейсу (cosmo-glass.css) і відсутність дублів тексту в шаблонах.

Розміри кнопок і відступи задаються токенами в одному місці; тест не дозволяє тихо розбігтися значенням і
перевіряє, що пояснювальні абзаци, які повторювали дані «Метрик», не повернулися.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app" / "static" / "css" / "cosmo-glass.css").read_text(encoding="utf-8")
TEMPLATES = {p.name: p.read_text(encoding="utf-8") for p in (ROOT / "app" / "templates").glob("*.html")}


def _token(name: str) -> str:
    m = re.search(rf"--{name}:\s*([^;]+);", CSS)
    assert m, f"немає токена --{name}"
    return m.group(1).strip()


def test_size_and_spacing_tokens_are_defined_once():
    assert _token("ctl-h") == "32px" and _token("ctl-r") == "10px" and _token("ctl-fs") == "12px"
    assert _token("gap") == "12px" and _token("gap-s") == "8px"
    assert _token("ctl-icon") == "28px"
    for name in ("ctl-h", "ctl-r", "ctl-fs", "gap", "gap-s"):
        assert len(re.findall(rf"--{name}:\s*[^;]+;", CSS)) == 1, f"токен --{name} оголошено кілька разів"


def test_controls_use_the_tokens_not_literal_sizes():
    block = CSS[CSS.index("Єдина шкала розмірів"):]
    heights = re.findall(r"(?<![-\w])height:\s*([^;!]+)", block)
    assert heights and all(h.strip() in ("var(--ctl-h)", "var(--ctl-icon)", "100%", "auto") for h in heights), heights
    assert "padding: var(--gap)" in block and "var(--gap-s)" in block


def test_no_explanatory_paragraphs_that_repeat_metrics():
    moon = TEMPLATES["moon.html"]
    base = TEMPLATES["base.html"]
    assert "Комірка Diviner" not in moon and "Наведіть курсор" not in moon
    assert "Спостерігач на поверхні" not in base, "джерела даних — у блоці «Джерела», а не в оверлеї метрик"
    # підсумки під графіками дублювали «Метрики» — елементи лишились порожніми (для повідомлень про помилки)
    assert re.search(r'id="timeline-summary"[^>]*></p>', moon)
    assert re.search(r'id="temp-summary"[^>]*></p>', moon)
    for name in ("_search.html", "mission.html", "plan.html", "launch_window.html"):
        html = TEMPLATES[name]
        heading_hint = re.search(r'<header class="results-heading"><h2>[^<]+</h2><p', html)
        assert not heading_hint, f"{name}: підказка в заголовку результатів"
