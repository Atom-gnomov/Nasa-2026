def test_index_redirects_to_moon(client):
    res = client.get("/")
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/moon")


def test_moon_page(client):
    res = client.get("/moon")
    assert res.status_code == 200
    assert "calendar-input" in res.get_data(as_text=True)
    assert "metrics-overlay" in res.get_data(as_text=True)
    assert 'id="site-header"' in res.get_data(as_text=True)


def test_moon_page_has_globe_controls(client):
    html = client.get("/moon").get_data(as_text=True)
    markers = ('data-view="globe"', 'data-view="map"', 'data-view="polar"', "grid-toggle", "relief", "globe_view.js")
    for marker in markers:
        assert marker in html


def test_globe_assets_served_from_cache_dir(app, tmp_path):
    (tmp_path / "globe").mkdir()
    (tmp_path / "globe" / "globe.json").write_text('{"version": 1}', encoding="utf-8")
    app.config["CACHE_DIR"] = tmp_path
    client = app.test_client()
    assert client.get("/assets/globe/globe.json").get_json() == {"version": 1}
    assert client.get("/assets/globe/missing.png").status_code == 404


def test_system_modes(client):
    for mode in ("earth-moon", "sun-moon-earth"):
        res = client.get(f"/system/{mode}")
        assert res.status_code == 200
        assert f'data-mode="{mode}"' in res.get_data(as_text=True)


def test_system_unknown_mode_falls_back(client):
    res = client.get("/system/unknown")
    assert 'data-mode="earth-moon"' in res.get_data(as_text=True)


def test_system_page_has_controls(client):
    html = client.get("/system/earth-moon").get_data(as_text=True)
    markers = ('data-focus="moonview"', 'id="system-scale"', 'id="system-play"', "system-facts", "system_view.js",
               "charts.js")
    for marker in markers:
        assert marker in html


def test_system_assets_served_from_cache_dir(app, tmp_path):
    (tmp_path / "system").mkdir()
    (tmp_path / "system" / "system.json").write_text('{"version": 2}', encoding="utf-8")
    app.config["CACHE_DIR"] = tmp_path
    client = app.test_client()
    assert client.get("/assets/system/system.json").get_json() == {"version": 2}
    assert client.get("/assets/system/missing.glb").status_code == 404


def test_search_is_a_separate_analytics_page(client):
    """Підбір має власний URL і не містить 3D-карти."""
    res = client.get("/search?lang=en&datetime=2027-07-01T00:00Z&lat=-85&lon=0")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    for marker in ('id="search"', 'id="s-run"', 'href="/search"', 'workspace_ui.js'):
        assert marker in html
    assert 'id="moon-globe"' not in html
    assert 'class="page-search"' in html


def test_mission_page_renders_with_tab_and_scripts(client):
    html = client.get("/mission").get_data(as_text=True)
    assert "Конфігуратор місії" in html
    assert 'id="m-crewed"' in html and 'id="m-system"' in html
    assert "js/mission.js" in html
    assert 'href="/mission"' in html  # вкладка «Місія» в навігації

def test_workspace_shell_is_shared_by_all_pages(client):
    paths = ("/moon", "/system", "/search", "/mission", "/plan")
    for path in paths:
        html = client.get(path).get_data(as_text=True)
        assert 'id="site-header"' in html, path
        assert 'id="calendar-input"' in html, path
        assert 'id="fullscreen-toggle"' in html, path
        assert 'css/workspace.css' in html, path
        assert 'js/workspace_ui.js' in html, path
        assert 'aria-current="page"' in html, path


def test_analytics_pages_do_not_include_moon_canvas(client):
    for path in ("/search", "/mission", "/plan"):
        html = client.get(path).get_data(as_text=True)
        assert 'id="moon-globe"' not in html
        assert 'class="results-heading"' in html


def test_scene_pages_preserve_both_canvas_and_controls(client):
    moon = client.get("/moon").get_data(as_text=True)
    system = client.get("/system").get_data(as_text=True)
    assert 'id="surface"' in moon and 'id="moon-globe"' in moon
    assert 'id="system-view"' in system and 'id="system-sim-controls"' in system

def test_header_navigation_is_one_scrollable_strip(client):
    for page in ("/moon", "/system", "/search", "/mission", "/plan"):
        html = client.get(page).get_data(as_text=True)
        assert 'id="header-middle"' in html
        assert 'class="header-actions"' in html
        assert html.index('class="brand"') < html.index('id="header-middle"') < html.index('class="header-actions"')
        assert html.count('class="cal-step-short"') == 6


def test_analytics_results_share_glass_panel_class(client):
    pages = ("/search", "/mission", "/plan")
    for url in pages:
        html = client.get(url).get_data(as_text=True)
        assert "workspace-results" in html, url
        assert 'class="results-heading"' in html, url


def test_orbital_glass_theme_is_included_last(client):
    """Every tab shares the same glass theme without moving layout logic."""
    for path in ("/moon", "/system", "/search", "/mission", "/plan"):
        html = client.get(path).get_data(as_text=True)
        assert "css/orbital-glass.css" in html, path
        assert html.index("css/style.css") < html.index("css/workspace.css") < html.index("css/orbital-glass.css"), path

def test_scene_dock_uses_compact_group_tabs(client):
    for route in ("/moon", "/system"):
        html = client.get(route).get_data(as_text=True)
        assert "js/workspace_ui.js" in html
        assert "css/workspace.css" in html


def test_report_page_is_step_10_of_the_wizard(client):
    html = client.get("/report").get_data(as_text=True)
    assert 'data-step="10"' in html and 'id="r-body"' in html and 'id="mp-steps"' in html
    assert "js/report.js" in html and 'id="r-print"' in html and 'id="r-md"' in html and 'id="r-json"' in html
    assert "workspace-results" in html and 'id="moon-globe"' not in html


def test_consistency_page_is_step_9_of_the_wizard(client):
    html = client.get("/consistency").get_data(as_text=True)
    assert 'data-step="9"' in html and 'id="c-list"' in html and 'id="mp-steps"' in html
    assert "js/consistency.js" in html and 'id="site-header"' in html
    assert "workspace-results" in html and 'class="results-heading"' in html
    assert 'id="moon-globe"' not in html


def test_saved_plans_panel_is_in_the_wizard_bar_of_every_page(client):
    for path in ("/moon", "/mission", "/plan", "/consistency", "/report"):
        html = client.get(path).get_data(as_text=True)
        assert 'id="mp-plans"' in html and "js/saved_plans.js" in html, path
        assert "mp-plans-save" in html and "mp-plans-export" in html and "mp-plans-import" in html, path


def test_mission_page_marks_each_control_with_its_wizard_step(client):
    html = client.get("/mission").get_data(as_text=True)
    for marker in ('data-step="2 4 6"', 'class="profile-slider" data-step="2"', 'id="m-days-row" data-step="4"',
                   'id="m-crew-row" data-step="6"', 'data-step="7"', 'data-step="8"'):
        assert marker in html, marker


def test_mission_toggle_button_and_initial_state_are_on_every_page(client):
    for path in ("/moon", "/system", "/search", "/mission", "/plan", "/consistency", "/report"):
        html = client.get(path).get_data(as_text=True)
        assert 'id="mp-toggle"' in html and "js/wizard_toggle.js" in html, path
        assert "lse-wizard" in html and "dataset.wizard" in html, path  # початковий стан до малювання, без блимання
        assert 'id="mp-steps"' in html and 'class="tabs"' in html, path  # нічого не видалено, лише ховається
        tabs = html[html.index('class="tabs"'):html.index('</nav>', html.index('class="tabs"'))]
        assert 'id="mp-toggle"' in tabs, path  # єдина кнопка планування — у смузі вкладок
        for link in ('/search', '/mission', '/plan'):  # вкладки планування сховано під неї, але є
            assert f'href="{link}"' in tabs and 'tab-plan' in tabs, (path, link)


def test_mobile_stylesheet_is_loaded_last_and_served(client):
    """F36: адаптація під телефони — окремий файл, що йде після всіх тем і перекриває десктопні правила шапки."""
    html = client.get("/moon").get_data(as_text=True)
    assert 'name="viewport"' in html
    assert html.index("css/mobile.css") > html.index("css/cosmo-glass.css")
    css = client.get("/static/css/mobile.css")
    assert css.status_code == 200
    text = css.get_data(as_text=True)
    assert "@media (max-width: 760px)" in text and "#calendar-input" in text
