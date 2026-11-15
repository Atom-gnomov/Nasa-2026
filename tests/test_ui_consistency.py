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
    # розміри елементів керування — до розділу вирівнювання, де малюються значки (7 px і т. ін. — геометрія іконок)
    block = CSS[CSS.index("Єдина шкала розмірів"):CSS.index("Вирівнювання (відгук)")]
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


def test_segmented_controls_are_flush_and_icons_are_drawn_by_css():
    """Перемикачі без щілин між кнопками; значки згортання — CSS-фігури (текстові символи зміщені шрифтом)."""
    assert re.search(r"\.seg,\s*\.seg\.mode-switch\s*\{\s*gap:\s*0\s*!important", CSS)
    assert ".dock-toggle::before" in CSS and ".widget-collapse::before" in CSS
    assert re.search(r"\.widget-action,\s*\.dock-toggle\s*\{[^}]*font-size:\s*0\s*!important", CSS)


def test_background_credit_is_text_in_the_help_menu_not_a_link_on_the_page():
    js = (ROOT / "app" / "static" / "js" / "starfield.js").read_text(encoding="utf-8")
    assert 'createElement("a")' not in js and "target = " not in js, "посилання на фон прибрано зі сторінки"
    assert ".help-menu-content" in js and "CC BY-NC-SA 4.0" in js, "ліцензія вимагає вказівки авторства"
    assert "position: fixed" not in CSS[CSS.index(".help-menu-content .sky-credit"):][:200]


def test_globe_status_is_only_the_cursor_coordinates_centred_above_the_dock():
    moon = TEMPLATES["moon.html"]
    assert 'id="globe-cursor"' in moon and 'id="globe-grid-label"' not in moon and 'id="globe-sun"' not in moon
    js = (ROOT / "app" / "static" / "js" / "globe_view.js").read_text(encoding="utf-8")
    assert "Курсор: ${fmtLat(hit.lat, 4)}, ${fmtLon(hit.lon, 4)}" in js
    assert "висота ${" not in js, "висота й температура не дописуються до рядка курсора"
    assert re.search(r"\.globe-status\s*\{[^}]*left:\s*50%[^}]*translateX\(-50%\)", CSS)


def test_back_button_is_styled_like_the_other_dock_buttons():
    block = CSS[CSS.index(".ui-surface-dock .surface-back"):][:600]
    assert "position: static" in block and "var(--cg-fill)" in block and "font-weight: 500" in block


def test_select_dropdown_menus_are_dark_with_light_text():
    """Системне меню <select> біле: світлий текст пунктів зникав. Меню має бути темним для всіх списків."""
    assert re.search(r"select option,\s*select optgroup\s*\{[^}]*background-color:\s*#[0-9a-f]{6}\s*!important", CSS)
    assert re.search(r"select option,\s*select optgroup\s*\{[^}]*color:\s*#f6f8fb\s*!important", CSS)
    assert re.search(r":root\s*\{\s*color-scheme:\s*dark", CSS)
