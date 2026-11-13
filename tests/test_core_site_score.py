import pytest

from app.core import site_score as ss


def summ(sun=0.5, night=100.0, comm=0.5, gap=100.0, svf=1.0, sun_h=300.0, comm_h=300.0, thermal=None):
    return {"sun_fraction": sun, "longest_night_h": night, "comm_fraction": comm, "longest_comm_gap_h": gap,
            "sky_view_fraction": svf, "sun_hours": sun_h, "comm_hours": comm_h, "thermal_fraction": thermal}


def test_factor_scales_match_math_doc():
    assert ss.energy_score(1.0, 0.0) == 1.0
    assert ss.energy_score(0.0, 354.0) == 0.0
    assert ss.energy_score(0.5, 177.0) == pytest.approx(0.5)
    assert ss.energy_score(0.5, 1000.0) == pytest.approx(0.3)  # ніч довша за опорну — внесок 0
    assert ss.comms_score(1.0, 0.0) == 1.0
    assert ss.comms_score(0.0, 336.0) == 0.0
    assert ss.radiation_score(1.0) == 0.0
    assert ss.radiation_score(0.6) == pytest.approx(1.0)
    assert ss.radiation_score(0.8) == pytest.approx(0.5)
    assert ss.temperature_score(0.7) == 0.7
    assert ss.temperature_score(1.4) == 1.0


def test_score_does_not_depend_on_other_candidates():
    a = summ(sun=0.9, night=20)
    alone = ss.score_points([a, summ()], ["energy", "comms"])
    crowded = ss.score_points([a, summ(), summ(sun=0.99, night=1), summ(sun=0.01, night=400)], ["energy", "comms"])
    score_a = next(p.score_pct for p in alone if p.index == 0)
    assert next(p.score_pct for p in crowded if p.index == 0) == score_a


def test_weights_follow_priority_order():
    w = ss.priority_weights(["comms", "energy", "radiation"])
    assert list(w) == ["comms", "energy", "radiation"]
    assert sum(w.values()) == pytest.approx(1.0)
    assert w["comms"] > w["energy"] > w["radiation"]
    with pytest.raises(ValueError):
        ss.priority_weights(["energy", "energy"])


def test_priority_order_changes_winner():
    sunny = summ(sun=0.9, night=10, comm=0.2, gap=300)
    talkative = summ(sun=0.2, night=300, comm=0.9, gap=10)
    assert ss.score_points([sunny, talkative], ["energy", "comms"])[0].index == 0
    assert ss.score_points([sunny, talkative], ["comms", "energy"])[0].index == 1


def test_maximin_prefers_balanced_point():
    balanced = summ(sun=0.6, night=100, comm=0.6, gap=100)
    lopsided = summ(sun=1.0, night=0, comm=0.0, gap=336)
    weighted = ss.score_points([balanced, lopsided], ["energy", "comms"], "weighted")
    maximin = ss.score_points([balanced, lopsided], ["energy", "comms"], "maximin")
    assert weighted[0].index == 1  # перекошена, але з важливою енергією
    assert maximin[0].index == 0
    assert maximin[0].score_pct == pytest.approx(100 * min(maximin[0].factors.values()), abs=0.01)


def test_requirements_make_points_infeasible_and_sort_last():
    good = summ(sun_h=500, comm_h=400)
    best_but_short = summ(sun=1.0, night=0, comm=1.0, gap=0, sun_h=100, comm_h=100)
    ranked = ss.score_points([best_but_short, good], ["energy", "comms"],
                             requirements=ss.Requirements(min_sun_hours=300, min_comm_hours=300))
    assert [p.index for p in ranked] == [1, 0]
    assert ranked[0].feasible and not ranked[1].feasible
    assert {v["requirement"] for v in ranked[1].violations} == {"min_sun_hours", "min_comm_hours"}
    assert ranked[1].pareto is False


def test_pareto_flags_only_non_dominated_feasible():
    a = summ(sun=0.9, night=10, comm=0.1, gap=300)
    b = summ(sun=0.1, night=300, comm=0.9, gap=10)
    c = summ(sun=0.05, night=350, comm=0.05, gap=330)  # домінована
    ranked = {p.index: p for p in ss.score_points([a, b, c], ["energy", "comms"])}
    assert ranked[0].pareto and ranked[1].pareto and not ranked[2].pareto


def test_missing_data_raises():
    with pytest.raises(ValueError, match="thermal_fraction"):
        ss.score_points([summ(), summ()], ["energy", "temperature"])
    with pytest.raises(ValueError):
        ss.score_points([summ()], [])
    with pytest.raises(ValueError):
        ss.score_points([summ()], ["energy"], mode="average")


def test_comparison_dominance_tradeoff_tie():
    w = ss.priority_weights(["energy", "comms"])
    strong = summ(sun=0.9, night=10, comm=0.9, gap=10)
    weak = summ(sun=0.3, night=200, comm=0.3, gap=200)
    r = ss.score_points([strong, weak], ["energy", "comms"])
    cmp_ = ss.compare(r[0], r[1], w)
    assert cmp_["dominance"] == "a" and cmp_["score_delta_pct"] > 0 and cmp_["weighted_advantage"] > 0
    assert all(f["winner"] == "a" for f in cmp_["per_factor"])
    assert ss.compare(r[1], r[0], w)["dominance"] == "b"

    sunny = summ(sun=0.9, night=10, comm=0.2, gap=300)
    talkative = summ(sun=0.2, night=300, comm=0.9, gap=10)
    r = ss.score_points([sunny, talkative], ["energy", "comms"])
    t = ss.compare(r[0], r[1], w)
    assert t["dominance"] == "tradeoff"
    assert t["decisive_factor"] in ("energy", "comms")

    same = ss.score_points([summ(), summ()], ["energy", "comms"])
    tie = ss.compare(same[0], same[1], w)
    assert tie["dominance"] == "tie" and tie["decisive_factor"] is None and tie["score_delta_pct"] == 0


def test_decisive_factor_is_weighted():
    # однакова різниця за двома факторами; ключовий — важливіший за пріоритетом
    a = summ(sun=0.8, night=0, comm=0.8, gap=0)
    b = summ(sun=0.3, night=0, comm=0.3, gap=0)
    w = ss.priority_weights(["comms", "energy"])
    r = ss.score_points([a, b], ["comms", "energy"])
    assert ss.compare(r[0], r[1], w)["decisive_factor"] == "comms"
