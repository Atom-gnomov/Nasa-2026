"""Модель ризику місії: запуск, перельот, посадка, системи, ризик втрати екіпажу (docs/MATH.md, §20; VISION).

Маса корисного навантаження сама по собі не змінює ймовірність відмови ракети, поки вона вкладається в можливості
ракети. Розмір категорій впливає на ризик опосередковано: заповненістю ракети (запас), кількістю пусків і стикувань,
масою модуля (складність посадки), складністю систем і — для екіпажу — резервуванням життєзабезпечення.

⚠️ УСІ ЙМОВІРНОСТІ Й КОЕФІЦІЄНТИ — ЕВРИСТИКА ДЛЯ ПОРІВНЯННЯ СЦЕНАРІЇВ, а не статистично доведені оцінки (статистика
запусків — журнал McDowell, посадок на Місяць мало). Тому результат подається діапазоном і словесною шкалою
(«низький … дуже високий»), а не одним відсотком. Чисті функції без Flask.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field

from app.core.launch import TRAJECTORIES

Range = tuple[float, float]

# Межі словесної шкали: ймовірність < межі → рівень (⚠️ орієнтовні, калібруються разом із формулами)
BANDS = ((0.05, "low"), (0.15, "moderate"), (0.35, "high"), (math.inf, "very_high"))
BAND_LABELS = {"low": "низький", "moderate": "помірний", "high": "високий", "very_high": "дуже високий"}


@dataclass(frozen=True)
class RiskParams:
    """⚠️ Евристичні значення (див. модуль)."""

    p_launch_base: float = 0.02  # відмова ракети в межах запасу (порядок для сучасних ракет)
    margin_start: float = 0.85  # заповненість, з якої зменшується запас
    margin_k: float = 1.0  # при заповненості 1 ризик запуску ·(1 + k) = подвоюється
    p_dock: float = 0.01  # ризик одного стикування на орбіті (коли кілька пусків)
    p_transit: Mapping[str, float] = field(default_factory=lambda: {"direct": 0.01, "low_energy": 0.02})
    p_landing_base: float = 0.20  # посадка модуля еталонної маси (історичних даних мало)
    landing_ref_kg: float = 1000.0
    landing_alpha: float = 0.4  # важчий модуль садити складніше: (m / m_ref)^α
    p_systems_base: float = 0.01
    p_systems_per_complexity: float = 0.04  # складність 0…1 — середній розмір категорій
    loc_given_failure: float = 0.5  # частка відмов, що призводять до втрати екіпажу
    loc_redundancy_gain: float = 0.4  # життєзабезпечення «Максимум» знижує її на 40 %
    loc_low_energy_factor: float = 1.5  # довгий політ: запаси, радіація в дорозі
    uncertainty: Range = (0.5, 2.0)  # діапазон ризику навколо оцінки


DEFAULT_PARAMS = RiskParams()


@dataclass(frozen=True)
class RiskAssessment:
    p_launch: float
    p_transit: float
    p_landing: float
    p_systems: float
    p_total: float
    p_total_range: Range
    band: str
    band_label: str
    launches: int
    p_crew_loss: float | None  # None — безпілотна місія
    p_crew_loss_range: Range | None
    crew_band: str | None
    crew_band_label: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def band(p: float) -> str:
    """Рівень словесної шкали для ймовірності."""
    if not 0.0 <= p <= 1.0:
        raise ValueError("Ймовірність має бути в межах 0…1")
    return next(name for limit, name in BANDS if p < limit)


def _clip(p: float) -> float:
    return min(1.0, max(0.0, p))


def _range(p: float, params: RiskParams) -> Range:
    return (_clip(p * params.uncertainty[0]), _clip(p * params.uncertainty[1]))


def _single_launch(u: float, params: RiskParams) -> float:
    """p = p_база · (1 + k · max(0, (u − 0,85)/0,15)²): біля межі ракети запас мізерний."""
    stress = max(0.0, (u - params.margin_start) / (1.0 - params.margin_start))
    return _clip(params.p_launch_base * (1.0 + params.margin_k * stress**2))


def launch_risk(utilization: float, params: RiskParams = DEFAULT_PARAMS) -> tuple[float, int]:
    """Ризик запуску(ів) і кількість пусків для заповненості u = маса на НОО / місткість ракети.

    u ≤ 1 — один пуск. u > 1 — n = ⌈u⌉ пусків із заповненістю u/n кожен, 1 − (1 − pᵢ)ⁿ, плюс n − 1 стикувань.
    """
    if utilization < 0:
        raise ValueError("Заповненість не може бути від'ємною")
    if utilization <= 1.0:
        return _single_launch(utilization, params), 1
    n = math.ceil(utilization)
    p_each = _single_launch(utilization / n, params)
    p = 1.0 - (1.0 - p_each) ** n * (1.0 - params.p_dock) ** (n - 1)
    return _clip(p), n


def landing_risk(mass_moon_kg: float, params: RiskParams = DEFAULT_PARAMS) -> float:
    """p = p_база · (m / m_еталон)^α, не більше 0,95."""
    if mass_moon_kg < 0:
        raise ValueError("Маса не може бути від'ємною")
    return min(0.95, params.p_landing_base * (mass_moon_kg / params.landing_ref_kg) ** params.landing_alpha)


def systems_risk(complexity: float, params: RiskParams = DEFAULT_PARAMS) -> float:
    if not 0.0 <= complexity <= 1.0:
        raise ValueError("Складність має бути в межах 0…1")
    return params.p_systems_base + params.p_systems_per_complexity * complexity


def assess(utilization: float, mass_moon_kg: float, sizes: Mapping[str, float], crew: int = 0,
           trajectory: str = "direct", params: RiskParams = DEFAULT_PARAMS) -> RiskAssessment:
    """Ризик місії: P = 1 − (1 − p_пуск)(1 − p_перельот)(1 − p_посадка)(1 − p_системи).

    sizes — розміри категорій 0…1 (equipment, life_support, comfort); для безпілотної місії враховується лише
    equipment. Ризик втрати екіпажу (crew > 0) = P · частка_відмов_до_втрати · (1 − виграш_резервування · s_лс) ·
    (множник довгого польоту для найекономнішої траєкторії).
    """
    if trajectory not in TRAJECTORIES:
        raise ValueError(f"Невідома траєкторія: {trajectory} (є {', '.join(TRAJECTORIES)})")
    if isinstance(crew, bool) or not isinstance(crew, int) or crew < 0:
        raise ValueError("crew має бути невід'ємним цілим")
    keys = ("equipment", "life_support", "comfort") if crew > 0 else ("equipment",)
    values = [float(sizes.get(k, 0.0)) for k in keys]
    if any(not 0.0 <= v <= 1.0 for v in values):
        raise ValueError("Розміри категорій мають бути в межах 0…1")

    p_launch, launches = launch_risk(utilization, params)
    p_transit = params.p_transit[trajectory]
    p_landing = landing_risk(mass_moon_kg, params)
    p_systems = systems_risk(sum(values) / len(values), params)
    p_total = 1.0 - (1.0 - p_launch) * (1.0 - p_transit) * (1.0 - p_landing) * (1.0 - p_systems)

    p_loc = loc_range = loc_band = None
    if crew > 0:
        redundancy = 1.0 - params.loc_redundancy_gain * float(sizes.get("life_support", 0.0))
        factor = params.loc_low_energy_factor if trajectory == "low_energy" else 1.0
        p_loc = _clip(p_total * params.loc_given_failure * redundancy * factor)
        loc_range, loc_band = _range(p_loc, params), band(p_loc)
    return RiskAssessment(
        p_launch=p_launch, p_transit=p_transit, p_landing=p_landing, p_systems=p_systems, p_total=p_total,
        p_total_range=_range(p_total, params), band=band(p_total), band_label=BAND_LABELS[band(p_total)],
        launches=launches, p_crew_loss=p_loc, p_crew_loss_range=loc_range, crew_band=loc_band,
        crew_band_label=BAND_LABELS[loc_band] if loc_band else None,
    )
