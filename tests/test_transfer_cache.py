"""Спільна пам'ять розрахунків переходу (правило «не рахувати одне двічі»)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.services import mission, ranking, transfer_cache

pytest.importorskip("naif_de440")

T0 = datetime(2027, 3, 1, tzinfo=timezone.utc)


def test_curve_is_computed_once_per_date_and_tof_set(app):
    with app.app_context():
        before = transfer_cache.cache_info()["curve"]
        tofs = [3.0, 4.0, 5.0]
        a = transfer_cache.dv_curve(T0 + timedelta(days=900), tofs)
        b = transfer_cache.dv_curve(T0 + timedelta(days=900), tofs)
        after = transfer_cache.cache_info()["curve"]
        assert [p.dv_total_m_s for p in a] == [p.dv_total_m_s for p in b]
        assert after["misses"] == before["misses"] + 1 and after["hits"] >= before["hits"] + 1
        assert a is not b  # кожен виклик отримує власний список


def test_options_are_shared_between_naive_and_aware_departures(app):
    with app.app_context():
        one = transfer_cache.transfer_options(datetime(2027, 3, 2))
        two = transfer_cache.transfer_options(datetime(2027, 3, 2, tzinfo=timezone.utc))
        assert one is two


def test_point_evaluation_reuses_the_expensive_timeline_part(app, monkeypatch):
    calls = []
    real = ranking.timeline.timeline

    def counting(*args, **kwargs):
        calls.append(args[:2])
        return real(*args, **kwargs)

    monkeypatch.setattr(ranking.timeline, "timeline", counting)
    ranking._timeline_core.cache_clear()
    with app.app_context():
        p = {"lat": -89.5, "lon": 12.0}
        from app.core.site_score import ScoreParams
        s1, src1, st1 = ranking.evaluate_point(p, T0, T0 + timedelta(days=5), 6.0, 0.0, False, ScoreParams())
        s2, src2, st2 = ranking.evaluate_point(p, T0, T0 + timedelta(days=5), 6.0, 0.0, False, ScoreParams())
        assert len(calls) == 1
        assert s1 == s2 and st1 == st2 and src1 == src2
        s2["sun_hours"] = -1  # зміна результату не псує кеш
        s3, _, _ = ranking.evaluate_point(p, T0, T0 + timedelta(days=5), 6.0, 0.0, False, ScoreParams())
        assert s3["sun_hours"] == s1["sun_hours"]


def test_payload_budget_is_computed_once_for_equal_inputs():
    mission._budget_cached.cache_clear()
    a = mission._budget({"equipment": "basic"}, 2, 10.0, 50.0, mission.payload.DEFAULT_PARAMS, None)
    b = mission._budget({"equipment": "basic"}, 2, 10.0, 50.0, mission.payload.DEFAULT_PARAMS, None)
    assert a is b
    assert mission._budget_cached.cache_info().hits == 1
    with pytest.raises(ValueError):
        mission._budget({"equipment": "basic"}, 99, 10.0, 0.0, mission.payload.DEFAULT_PARAMS, None)
