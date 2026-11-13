"""Оцінка й порівняння точок на Місяці (docs/MATH.md, §19).

Ідея: кожен фактор переводиться в оцінку 0…1 за **абсолютними** шкалами (а не мін-макс по поточній
вибірці), тому оцінка точки не залежить від того, які ще точки порівнюються, і результати різних
пошуків можна зіставляти. Ваги беруться з порядку пріоритетів (ROC, app.core.scoring).

Вхід — підсумки точки за період (словник `PointSummary`):
    sun_fraction, longest_night_h, sun_hours,
    comm_fraction, longest_comm_gap_h, comm_hours,
    sky_view_fraction   (для фактора radiation),
    thermal_fraction    (для фактора temperature).
Чисті функції на numpy/stdlib: без Flask і без звернень до даних.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field

import numpy as np

from app.core import scoring

FACTORS = ("energy", "comms", "radiation", "temperature")
MODES = ("weighted", "maximin")
TIE_EPS = 0.02  # різниця оцінок менша за це — нічия


@dataclass(frozen=True)
class ScoreParams:
    """Опорні шкали. Значення за замовчуванням — у docs/MATH.md, §19.2; змінюються з клієнта."""

    night_ref_h: float = 354.0  # половина синодичного місяця: ніч такої довжини — найгірший випадок
    comm_gap_ref_h: float = 336.0  # 14 діб без зв'язку — найгірший випадок
    energy_sun_weight: float = 0.6  # частка освітленості в оцінці енергії (решта — коротка ніч)
    comms_time_weight: float = 0.7  # частка часу зв'язку в оцінці зв'язку (решта — короткі розриви)
    shield_ref: float = 0.4  # екранування неба, при якому оцінка радіації = 1 (відкрите небо 0,6)
    temp_min_k: float = 233.15  # −40 °C
    temp_max_k: float = 333.15  # +60 °C

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Requirements:
    min_sun_hours: float | None = None
    min_comm_hours: float | None = None


@dataclass
class ScoredPoint:
    index: int  # позиція у вхідному списку
    factors: dict[str, float]
    score_pct: float
    feasible: bool
    violations: list[dict]
    pareto: bool = False
    rank: int = 0
    summary: Mapping[str, float] = field(default_factory=dict)


DEFAULT_PARAMS = ScoreParams()
NO_REQUIREMENTS = Requirements()


def _clip01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


# --- оцінки факторів ---------------------------------------------------------------------------

def energy_score(sun_fraction: float, longest_night_h: float, p: ScoreParams = DEFAULT_PARAMS) -> float:
    """w·f_сонце + (1 − w)·(1 − min(ніч / N_ref, 1)): багато світла й коротка ніч (менші акумулятори)."""
    night = 1.0 - min(max(longest_night_h, 0.0) / p.night_ref_h, 1.0)
    return _clip01(p.energy_sun_weight * _clip01(sun_fraction) + (1 - p.energy_sun_weight) * night)


def comms_score(comm_fraction: float, longest_gap_h: float, p: ScoreParams = DEFAULT_PARAMS) -> float:
    """w·f_зв'язок + (1 − w)·(1 − min(розрив / G_ref, 1)): частий зв'язок і короткі розриви."""
    gap = 1.0 - min(max(longest_gap_h, 0.0) / p.comm_gap_ref_h, 1.0)
    return _clip01(p.comms_time_weight * _clip01(comm_fraction) + (1 - p.comms_time_weight) * gap)


def radiation_score(sky_view_fraction: float, p: ScoreParams = DEFAULT_PARAMS) -> float:
    """clip((1 − Ω/2π) / S_ref): чим більше неба закрито рельєфом, тим менша доза ГКП (доза ∝ Ω/2π)."""
    return _clip01((1.0 - sky_view_fraction) / p.shield_ref)


def temperature_score(thermal_fraction: float) -> float:
    """Частка місячної доби, коли температура поверхні в робочому діапазоні (проксі складності терморегуляції)."""
    return _clip01(thermal_fraction)


_NEEDS = {
    "energy": ("sun_fraction", "longest_night_h"),
    "comms": ("comm_fraction", "longest_comm_gap_h"),
    "radiation": ("sky_view_fraction",),
    "temperature": ("thermal_fraction",),
}


def factor_scores(summary: Mapping[str, float | None], factors: Sequence[str],
                  p: ScoreParams = DEFAULT_PARAMS) -> dict[str, float]:
    """Оцінки 0…1 для вибраних факторів. Якщо для фактора немає даних — ValueError."""
    out: dict[str, float] = {}
    for f in factors:
        if f not in _NEEDS:
            raise ValueError(f"Невідомий фактор: {f}")
        missing = [k for k in _NEEDS[f] if summary.get(k) is None]
        if missing:
            raise ValueError(f"Для фактора {f} немає даних: {', '.join(missing)}")
        if f == "energy":
            out[f] = energy_score(summary["sun_fraction"], summary["longest_night_h"], p)
        elif f == "comms":
            out[f] = comms_score(summary["comm_fraction"], summary["longest_comm_gap_h"], p)
        elif f == "radiation":
            out[f] = radiation_score(summary["sky_view_fraction"], p)
        else:
            out[f] = temperature_score(summary["thermal_fraction"])
    return out


# --- допустимість, ранжування, порівняння ------------------------------------------------------

def violations(summary: Mapping[str, float | None], req: Requirements) -> list[dict]:
    out = []
    for key, value_key, required in (("min_sun_hours", "sun_hours", req.min_sun_hours),
                                     ("min_comm_hours", "comm_hours", req.min_comm_hours)):
        if required is None:
            continue
        value = summary.get(value_key)
        if value is None or value < required:
            out.append({"requirement": key, "value": float(value or 0.0), "required": float(required)})
    return out


def priority_weights(priorities: Sequence[str]) -> dict[str, float]:
    """Ваги ROC за порядком (перший — найважливіший); сума = 1."""
    if len(set(priorities)) != len(priorities):
        raise ValueError("Фактори в пріоритетах мають бути унікальними")
    return dict(zip(priorities, scoring.roc_weights(len(priorities)).tolist(), strict=True))


def score_points(summaries: Sequence[Mapping[str, float | None]], priorities: Sequence[str],
                 mode: str = "weighted", requirements: Requirements = NO_REQUIREMENTS,
                 params: ScoreParams = DEFAULT_PARAMS) -> list[ScoredPoint]:
    """Оцінює й ранжує точки. Повертає список у порядку рангу (rank = 1 — найкраща).

    Порядок: допустимі перед недопустимими; далі за балом; при рівності — за найгіршим фактором,
    потім за вхідним порядком. `pareto` — серед допустимих.
    """
    if mode not in MODES:
        raise ValueError(f"Невідомий режим: {mode}")
    if not priorities:
        raise ValueError("Потрібен щонайменше один фактор")
    weights = priority_weights(priorities)
    w = np.array([weights[f] for f in priorities])

    points: list[ScoredPoint] = []
    for i, summary in enumerate(summaries):
        fs = factor_scores(summary, priorities, params)
        vec = np.array([fs[f] for f in priorities])
        score = 100.0 * (float(vec @ w) if mode == "weighted" else float(vec.min()))
        viol = violations(summary, requirements)
        points.append(ScoredPoint(i, fs, round(score, 2), not viol, viol, summary=summary))

    feasible = [p for p in points if p.feasible]
    if feasible:
        matrix = np.array([[p.factors[f] for f in priorities] for p in feasible])
        for k in scoring.pareto_front(matrix):
            feasible[int(k)].pareto = True

    points.sort(key=lambda p: (not p.feasible, -p.score_pct, -min(p.factors.values()), p.index))
    for rank, p in enumerate(points, start=1):
        p.rank = rank
    return points


def compare(a: ScoredPoint, b: ScoredPoint, weights: Mapping[str, float], eps: float = TIE_EPS) -> dict:
    """Порівняння двох оцінених точок: різниця по факторах, домінування чи компроміс, визначальний фактор.

    dominance: «a» — a не гірша за всіма факторами (з допуском eps) і краща хоча б за одним; «b» — навпаки;
    «tie» — різниці в межах допуску за всіма факторами; «tradeoff» — виграш за одними коштує програшу за іншими.
    """
    per_factor = []
    for f in weights:
        delta = a.factors[f] - b.factors[f]
        winner = "tie" if abs(delta) <= eps else ("a" if delta > 0 else "b")
        per_factor.append({"factor": f, "a": round(a.factors[f], 4), "b": round(b.factors[f], 4),
                           "delta": round(delta, 4), "winner": winner})
    wins_a = sum(r["winner"] == "a" for r in per_factor)
    wins_b = sum(r["winner"] == "b" for r in per_factor)
    dominance = "tie" if not (wins_a or wins_b) else "a" if not wins_b else "b" if not wins_a else "tradeoff"
    contributions = {r["factor"]: weights[r["factor"]] * r["delta"] for r in per_factor}
    decisive = max(contributions, key=lambda k: abs(contributions[k])) if wins_a or wins_b else None
    return {
        "a_rank": a.rank, "b_rank": b.rank,
        "score_delta_pct": round(a.score_pct - b.score_pct, 2),
        "dominance": dominance,
        "per_factor": per_factor,
        "decisive_factor": decisive,
        "weighted_advantage": round(sum(contributions.values()), 4),
    }
