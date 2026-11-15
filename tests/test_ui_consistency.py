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
    assert _token("ctl-h") == "32px" and _token("ctl-r") == "0" and _token("ctl-fs") == "12px"
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


def test_flat_corners_and_no_glow_but_glass_stays():
    """Прямі кути й жодного світіння; ефект скла (розмиття, прозора заливка, тонка рамка) лишається."""
    assert re.search(r"\*,\s*\*::before,\s*\*::after\s*\{[^}]*border-radius:\s*0\s*!important", CSS)
    universal = r"\*,\s*\*::before,\s*\*::after\s*\{[^}]*"
    assert re.search(universal + r"box-shadow:\s*none\s*!important[^}]*text-shadow:\s*none\s*!important", CSS)
    assert re.search(r"\.widget-title::before[^{]*\{[^}]*content:\s*none", CSS), "точки біля заголовків прибрано"
    assert "backdrop-filter" in CSS and "--cg-fill" in CSS and "--cg-line" in CSS, "ефект скла лишається"


def test_header_corner_is_only_the_logo_and_intro_assets_exist():
    base = TEMPLATES["base.html"]
    brand = re.search(r'<a class="brand".*?</a>', base, re.S).group(0)
    assert "brand-logo" in brand and "img/logo.png" in brand
    assert re.sub(r"<[^>]+>", "", brand).strip() == "Lunar Mission Builder", "біля лого — назва сайту"
    assert "Lunar Site Explorer" not in base and 'class="intro-title">Lunar Mission Builder' in base
    static = ROOT / "app" / "static"
    assert (static / "img" / "logo.png").stat().st_size > 0
    assert (static / "media" / "logo_intro.webm").stat().st_size < 1_000_000, "заставка легка"
    assert 'id="intro"' in base and "media/logo_intro.webm" in base and "js/intro.js" in base
    assert "intro-pending" in base and "lse-intro" in base and "prefers-reduced-motion" in base
    js = (static / "js" / "intro.js").read_text(encoding="utf-8")
    assert "ended" in js and "Escape" in js and "sessionStorage" in js


def test_scenes_are_full_bleed_so_widgets_float_on_one_space():
    block = CSS[CSS.index("Єдиний простір"):]
    hosts = r"#moon-globe, body\.page-system #system-view, body\.page-moon #surface\s*\{"
    assert re.search(hosts + r"[^}]*top:\s*0\s*!important[^}]*left:\s*0\s*!important", block)
    scene_js = (ROOT / "app" / "static" / "js" / "three" / "scene.js").read_text(encoding="utf-8")
    assert "setViewOffset" in scene_js and "--scene-left" in scene_js, "центр кадру зсунуто у вільну ділянку"


def test_one_monospace_font_for_all_text_including_canvas_labels():
    """Єдиний шрифт — той самий, що й у значеннях «Метрик»; тексти на canvas теж ним."""
    cosmos = (ROOT / "app/static/css/cosmos.css").read_text(encoding="utf-8")
    stack = re.search(r"--cx-font-num:\s*([^;]+);", cosmos).group(1)
    assert _token("font") == stack.strip()
    assert re.search(r"\*,\s*\*::before,\s*\*::after\s*\{\s*font-family:\s*var\(--font\)\s*!important", CSS)
    for name in ("charts.js", "globe_view.js", "surface_view.js"):
        js = (ROOT / "app/static/js" / name).read_text(encoding="utf-8")
        assert "system-ui" not in js, name


def test_intro_waits_for_a_stable_sky_and_dims_it_to_75_percent():
    """Заставка стартує, коли небо намальоване й не змінюється, тож тло не блимає; під відео воно затемнене на 75 %."""
    star = (ROOT / "app/static/js/starfield.js").read_text(encoding="utf-8")
    assert "sky-ready" in star and "__skyReady" in star and "markSkyReady()" in star
    intro = (ROOT / "app/static/js/intro.js").read_text(encoding="utf-8")
    assert "sky-ready" in intro and "SKY_WAIT_MS" in intro, "є запасний таймер, якщо небо не готове"
    assert re.search(r"html\.intro-playing #intro\s*\{\s*background:\s*rgba\(0,\s*0,\s*0,\s*\.75\)", CSS)


def test_static_urls_carry_a_content_hash_and_intro_warms_the_cache():
    from app import create_app

    html = create_app().test_client().get("/moon").get_data(as_text=True)
    assert re.search(r"/static/css/cosmo-glass\.css\?v=[0-9a-f]{10}", html)
    assert '/static/js/starfield.js"' in html, "модулі без ?v=: імпорти інших модулів дали б другий екземпляр"
    intro = (ROOT / "app/static/js/intro.js").read_text(encoding="utf-8")
    assert "warmCache" in intro and "globe.json" in intro and "system.json" in intro
    assert 'id="intro-anim"' in html and 'width="720"' in html


def test_intro_flashes_after_the_glint_then_logo_fades_and_ui_lights_up():
    base = TEMPLATES["base.html"]
    assert 'class="intro-flash"' in base
    assert "@keyframes intro-flash" in CSS and re.search(r"#intro\.is-leaving video\s*\{[^}]*opacity:\s*0", CSS)
    assert re.search(r"#intro\.is-leaving\s*\{[^}]*background-color:\s*rgba\(0,\s*0,\s*0,\s*0\)", CSS)
    js = (ROOT / "app/static/js/intro.js").read_text(encoding="utf-8")
    assert 'addEventListener("ended", finish)' in js


def test_first_paint_is_gated_so_pages_do_not_flash_between_languages_or_layouts():
    base = TEMPLATES["base.html"]
    assert "ui-pending" in base and "window.__gate" in base and "navigator.languages" in base
    static = ROOT / "app" / "static" / "js"
    assert 'window.__gate?.("i18n")' in (static / "i18n.js").read_text(encoding="utf-8")
    assert 'window.__gate?.("ui")' in (static / "workspace_ui.js").read_text(encoding="utf-8")
    assert "html.ui-pending body" in CSS and "@view-transition" in CSS
    assert "opacity .7s" in (static / "three" / "scene.js").read_text(encoding="utf-8"), "планета проявляється плавно"


def test_mode_switches_are_smooth_and_cheap():
    """Режими: без перевиділення буфера, прихована сцена не малюється, 3D прогріте, плавне гасіння/проявлення."""
    js = ROOT / "app" / "static" / "js"
    scene = (js / "three" / "scene.js").read_text(encoding="utf-8")
    assert "lastKey" in scene and "checkVisibility" in scene
    sv = (js / "surface_view.js").read_text(encoding="utf-8")
    assert "warmed" in sv and "showPane" in sv and "surface-active" in sv
    gv = (js / "globe_view.js").read_text(encoding="utf-8")
    assert '"scene-mode"' in gv and "globeAsleep" in gv
    assert '"scene-mode"' in (js / "workspace_ui.js").read_text(encoding="utf-8")
    assert re.search(r"body\.page-moon #surface\s*\{[^}]*display:\s*block\s*!important[^}]*opacity:\s*0", CSS)
    assert "speculationrules" in TEMPLATES["base.html"]


def test_system_page_does_not_jump_on_entry():
    """Вхід у «Систему»: камера одразу на місці, полотно проявляється, коли є тіла (без підльоту)."""
    js = ROOT / "app" / "static" / "js"
    sv = (js / "system_view.js").read_text(encoding="utf-8")
    assert "camAnim.t0 = -1e9" in sv and "fade: false" in sv and "ctx.reveal()" in sv
    assert "fade = true" in (js / "three" / "scene.js").read_text(encoding="utf-8")


def test_select_menu_is_a_styled_popup_inside_the_panel_and_focus_ring_is_single():
    """Меню списку — елемент зі стилем інтерфейсу (не біле системне): не ширше списку в панелі, одна рамка фокусу."""
    assert "@supports (appearance: base-select)" in CSS and "select::picker(select)" in CSS
    assert re.search(r"\.ui-widget select::picker\(select\)\s*\{[^}]*width:\s*anchor-size\(width\)", CSS)
    assert re.search(r"select:focus-visible[^{]*\{[^}]*outline-offset:\s*-1px", CSS), "фокус — тонка рамка всередині"
    assert "button:not([class]):not(:disabled)" in CSS and "#calendar-input { background: var(--cg-fill-faint)" in CSS


def test_site_starts_on_the_moon_page_and_flight_uses_the_rocket_model():
    base = TEMPLATES["base.html"]
    assert 'lse-started' in base and 'location.replace("/moon"' in base
    sv = (ROOT / "app" / "static" / "js" / "system_view.js").read_text(encoding="utf-8")
    assert "prepareRocketModel" in sv and "rocketMesh, simRocket" in sv and "rocket.credit" in sv
    assert "CC BY 4.0" in (ROOT / "tools" / "import_rocket_model.py").read_text(encoding="utf-8")


def test_rocket_is_drawn_at_true_scale_with_a_follow_camera():
    """Ракета — справжнього розміру відносно планети (98,3 м, довідник NASA SLS), камера «Ракета» і маркер положення."""
    sv = (ROOT / "app" / "static" / "js" / "system_view.js").read_text(encoding="utf-8")
    assert "rocketKm / bodyKm" in sv and "98.3" in sv and 'focus === "rocket"' in sv and "rocketDot" in sv
    assert 'data-focus="rocket"' in TEMPLATES["system.html"]
    tool = (ROOT / "tools" / "import_rocket_model.py").read_text(encoding="utf-8")
    assert '"length_m": 98.3' in tool and "sls_reference_guide_2022_web.pdf" in tool


def test_one_typography_scale_and_one_disabled_look_on_every_page():
    """Підписи, підказки, заголовки, списки й вимкнені кнопки — з однієї шкали, а не окремі розміри на сторінках."""
    assert _token("fs-s") == "12px" and _token("fs-m") == "13px" and _token("fs-l") == "15px"
    assert re.search(r"\nlabel\s*\{[^}]*font-size:\s*var\(--fs-s\)\s*!important[^}]*color:\s*var\(--cg-muted\)", CSS)
    assert re.search(r"\nh2\s*\{[^}]*font-size:\s*var\(--fs-l\)\s*!important", CSS)
    assert re.search(r"\nbutton:disabled:not\(\.primary\)\s*\{[^}]*var\(--cg-fill-faint\)", CSS)
    assert "li, .compare-note { font-size: var(--fs-m) !important" in CSS
