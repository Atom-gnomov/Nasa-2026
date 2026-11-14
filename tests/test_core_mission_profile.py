"""Профілі місії (app/core/mission_profile.py, M17): пороги з джерел, пріоритети, перевизначення."""

import json
from pathlib import Path

import pytest

from app.core import mission_profile as mp
from app.core import site_score

THRESHOLDS = json.loads(
    (Path(__file__).resolve().parents[1] / "app" / "data" / "mission_thresholds.json").read_text(encoding="utf-8"))


def test_uncrewed_has_no_crew_no_limits_and_default_priorities():
    p = mp.resolve("uncrewed", THRESHOLDS)
    assert p.crew == 0 and not p.life_support_enabled and not p.comfort_enabled
    assert p.limits == {}
    assert p.priorities == ("energy", "comms")
    assert p.from_profile == ("priorities",)
    assert p.requirements(708.7).min_sun_hours is None


def test_crewed_takes_every_published_threshold_for_the_profile():
    p = mp.resolve("crewed", THRESHOLDS, crew=4)
    assert p.crew == 4 and p.life_support_enabled and p.comfort_enabled
    expected = {row["quantity"] for row in THRESHOLDS if row["profile"] in ("crewed", "any")}
    assert set(p.limits) == expected
    slope = p.limit("landing_slope_deg")
    assert (slope.comparison, slope.value, slope.unit, slope.kind) == ("<", 10, "deg", "requirement")
    assert slope.id == "landing-slope-100m"
    assert p.limit("direct_to_earth_comm").value is None  # якісна вимога без числа
    assert p.priorities[0] == "radiation"
    assert set(p.priorities) <= set(site_score.FACTORS)
    assert "limits.landing_slope_deg" in p.from_profile and "crew" not in p.from_profile


def test_crewed_requirements_hard_slope_and_soft_visibility_from_sources():
    """M23: нахил посадки (вимога документа) — жорстка; видимість Землі й Сонця (фільтри відбору) — м'які."""
    req = mp.resolve("crewed", THRESHOLDS, crew=2).requirements()
    assert req.max_slope_deg == 10  # Artemis III: нахил ділянки посадки < 10°
    assert req.min_earth_fraction == pytest.approx(0.25)
    assert req.min_sun_fraction == pytest.approx(0.05)
    assert req.min_sun_hours is None and req.min_comm_hours is None  # годин не задаємо: порогу зв'язку немає (D5)


def test_uncrewed_profile_sets_no_landing_requirements():
    """Для безпілотної порогів у документах NASA немає: вимог за замовчуванням немає, користувач задає їх сам."""
    assert mp.resolve("uncrewed", THRESHOLDS).requirements() == site_score.Requirements()


def test_overridden_slope_limit_changes_the_requirement_and_removed_limit_drops_it():
    tighter = mp.resolve("crewed", THRESHOLDS, crew=2, limit_overrides={"landing_slope_deg": 6})
    assert tighter.requirements().max_slope_deg == 6.0
    removed = mp.resolve("crewed", THRESHOLDS, crew=2, limit_overrides={"landing_slope_deg": None,
                                                                         "earth_visible_fraction": None})
    req = removed.requirements()
    assert req.max_slope_deg is None and req.min_earth_fraction is None and req.min_sun_fraction == pytest.approx(0.05)


def test_explicit_values_win_over_the_profile():
    p = mp.resolve("crewed", THRESHOLDS, crew=3, priorities=["energy", "comms"],
                   limit_overrides={"landing_slope_deg": 6, "sun_visible_fraction": None})
    assert p.priorities == ("energy", "comms")
    slope = p.limit("landing_slope_deg")
    assert slope.value == 6.0 and slope.comparison == "<" and slope.id == "override"
    assert "sun_visible_fraction" not in p.limits and p.requirements(700).min_sun_hours is None
    assert "priorities" not in p.from_profile and "limits.landing_slope_deg" not in p.from_profile
    assert "limits.eva_slope_deg" in p.from_profile  # решту профіль усе ще задає


def test_default_crew_for_crewed_is_marked_as_profile_choice():
    p = mp.resolve("crewed", THRESHOLDS)
    assert p.crew == mp.MIN_CREW_CREWED_DEFAULT and "crew" in p.from_profile


@pytest.mark.parametrize("kwargs", [
    {"profile": "uncrewed", "crew": 2},
    {"profile": "crewed", "crew": 0},
    {"profile": "crewed", "crew": 99},
    {"profile": "crewed", "crew": True},
    {"profile": "crewed", "crew": 2.5},
    {"profile": "robot"},
    {"profile": "crewed", "priorities": ["energy", "fun"]},
    {"profile": "crewed", "priorities": ["energy", "energy"]},
    {"profile": "crewed", "limit_overrides": {"no_such_quantity": 1}},
    {"profile": "crewed", "limit_overrides": {"direct_to_earth_comm": 5}},
    {"profile": "uncrewed", "limit_overrides": {"landing_slope_deg": 5}},
])
def test_invalid_input_is_rejected(kwargs):
    with pytest.raises(ValueError):
        mp.resolve(thresholds=THRESHOLDS, **kwargs)


def test_two_thresholds_of_one_quantity_are_an_error():
    rows = [r for r in THRESHOLDS if r["quantity"] == "landing_slope_deg"]
    twin = dict(rows[0], id="landing-slope-twin")
    with pytest.raises(ValueError):
        mp.resolve("crewed", [*THRESHOLDS, twin], crew=2)


def test_any_profile_thresholds_apply_to_both():
    rows = [{"id": "x", "profile": "any", "quantity": "q", "comparison": "<", "value": 1, "unit": "u",
             "kind": "requirement", "scope": "s"}]
    assert "q" in mp.resolve("uncrewed", rows).limits and "q" in mp.resolve("crewed", rows, crew=1).limits


def test_to_dict_is_json_serialisable_and_lists_sources():
    d = mp.resolve("crewed", THRESHOLDS, crew=2).to_dict()
    json.dumps(d)
    assert d["categories"] == {"life_support": True, "comfort": True}
    assert d["limits"]["landing_slope_deg"]["id"] == "landing-slope-100m"
