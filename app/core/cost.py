"""Маса на низькій опорній орбіті (НОО) і вартість польоту (docs/MATH.md, §20; VISION: «Корисне навантаження»).

Маса на Місяці множиться паливом на посадку й розгін до Місяця за формулою Ціолковського; вартість =
запуск (ціна за кг на НОО з поправкою на широту старту) + корисне навантаження + модуль. Результати — діапазони
мін–макс, а не одне число: ціни орієнтовні.

⚠️ ТАБЛИЦІ ЦІН І ПАРАМЕТРИ РАКЕТИ ТУТ — ТИМЧАСОВІ ОРІЄНТОВНІ ЗНАЧЕННЯ (чекають D4). Ланцюжок Δv, Isp та інертної
маси відповідає MATH.md §13; ціна запуску ~ $2 700/кг на НОО — порядок величини для багаторазової ракети
(CSIS / Our World in Data, див. RESOURCES.md). Чисті функції без Flask.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field

from app.core.constants import EARTH_EQUATOR_ROTATION_M_S
from app.core.launch import TRAJECTORIES, rotation_boost_m_s

G0 = 9.80665
Range = tuple[float, float]


@dataclass(frozen=True)
class TransferParams:
    """Ланцюжок НОО → Місяць (⚠️ приклад із MATH.md §13: розгін до Місяця + посадка)."""

    dv_tli_m_s: float = 3130.0
    isp_tli_s: float = 450.0
    dv_landing_m_s: Mapping[str, float] = field(default_factory=lambda: {"direct": 2700.0, "low_energy": 2400.0})
    isp_landing_s: float = 320.0
    inert_fraction: float = 0.10  # інертна маса баків і ступеня — частка від маси палива
    isp_launch_s: float = 330.0  # середня питома тяга підйому на НОО (для поправки на широту)


@dataclass(frozen=True)
class Rocket:
    """⚠️ Типова орієнтовна ракета (вибір конкретної ракети відкладено)."""

    name: str = "типова (орієнтовна)"
    capacity_leo_kg: float = 17_500.0
    price_usd_per_kg: Range = (2_000.0, 5_000.0)
    failure_probability: float = 0.02  # база для моделі ризику (M14)


@dataclass(frozen=True)
class CostTable:
    """⚠️ Тимчасові діапазони цін, $ за кг (чекають D4)."""

    equipment_usd_per_kg: Range = (100_000.0, 400_000.0)
    life_support_usd_per_kg: Range = (30_000.0, 120_000.0)
    comfort_usd_per_kg: Range = (20_000.0, 80_000.0)
    lander_usd_per_kg: Range = (50_000.0, 150_000.0)  # конструкція, енергетика, запас


DEFAULT_TRANSFER = TransferParams()
DEFAULT_ROCKET = Rocket()
DEFAULT_TABLE = CostTable()


@dataclass(frozen=True)
class CostEstimate:
    trajectory: str
    mass_moon_kg: float
    mass_ratio: float
    mass_leo_kg: float
    site_factor: float
    launches: int
    utilization: float
    flight_time_days: Range
    launch_usd: Range
    payload_usd: Range
    lander_usd: Range
    total_usd: Range

    def to_dict(self) -> dict:
        return asdict(self)


def _trajectory(name: str) -> str:
    if name not in TRAJECTORIES:
        raise ValueError(f"Невідома траєкторія: {name} (є {', '.join(TRAJECTORIES)})")
    return name


def mass_ratio(trajectory: str, params: TransferParams = DEFAULT_TRANSFER) -> float:
    """Кг на НОО на 1 кг на Місяці. Для кожного ступеня: 1 + (e^{Δv/(g₀·Isp)} − 1)(1 + k), k — інертна частка;
    результат — добуток ступенів посадки й розгону до Місяця."""
    traj = _trajectory(trajectory)

    def stage(dv: float, isp: float) -> float:
        return 1.0 + (math.exp(dv / (G0 * isp)) - 1.0) * (1.0 + params.inert_fraction)

    return stage(params.dv_landing_m_s[traj], params.isp_landing_s) * stage(params.dv_tli_m_s, params.isp_tli_s)


def mass_leo(mass_moon_kg: float, trajectory: str, params: TransferParams = DEFAULT_TRANSFER) -> float:
    if mass_moon_kg < 0:
        raise ValueError("Маса не може бути від'ємною")
    return mass_moon_kg * mass_ratio(trajectory, params)


def site_factor(latitude_deg: float, params: TransferParams = DEFAULT_TRANSFER) -> float:
    """Поправка до маси на НОО за широтою старту: менша прибавка від обертання Землі → більше палива.

    k = exp(Δv_втрата / (g₀·Isp)), Δv_втрата = v_екватор − v_екватор·cos φ. На екваторі k = 1.
    """
    if not -90.0 <= latitude_deg <= 90.0:
        raise ValueError("Широта має бути в межах −90…90")
    lost = EARTH_EQUATOR_ROTATION_M_S - float(rotation_boost_m_s(latitude_deg))
    return math.exp(lost / (G0 * params.isp_launch_s))


def launches_needed(mass_leo_kg: float, rocket: Rocket = DEFAULT_ROCKET) -> int:
    return max(1, math.ceil(mass_leo_kg / rocket.capacity_leo_kg))


def utilization(mass_leo_kg: float, rocket: Rocket = DEFAULT_ROCKET) -> float:
    """Заповненість ракети: маса на НОО / місткість; > 1 — потрібна більша ракета або кілька пусків."""
    return mass_leo_kg / rocket.capacity_leo_kg


def _scale(price: Range, mass_kg: float) -> Range:
    return (price[0] * mass_kg, price[1] * mass_kg)


def _add(*ranges: Range) -> Range:
    return (sum(r[0] for r in ranges), sum(r[1] for r in ranges))


def mission_cost(masses_kg: Mapping[str, float], trajectory: str = "direct", latitude_deg: float = 0.0,
                 rocket: Rocket = DEFAULT_ROCKET, table: CostTable = DEFAULT_TABLE,
                 transfer: TransferParams = DEFAULT_TRANSFER) -> CostEstimate:
    """Вартість польоту за масами складових (ключі: equipment, life_support, comfort, power_system, structure, margin).

    Запуск = маса на НОО · поправка на широту · ціна за кг ракети; навантаження — за ціною кг кожної категорії;
    модуль — конструкція + енергетика + запас за ціною кг модуля.
    """
    traj = _trajectory(trajectory)
    get = lambda key: float(masses_kg.get(key, 0.0))  # noqa: E731
    if any(v < 0 for v in masses_kg.values()):
        raise ValueError("Маси не можуть бути від'ємними")
    mass_moon = sum(masses_kg.values())
    ratio = mass_ratio(traj, transfer)
    leo = mass_moon * ratio
    k_site = site_factor(latitude_deg, transfer)
    launch = _scale(rocket.price_usd_per_kg, leo * k_site)
    payload = _add(_scale(table.equipment_usd_per_kg, get("equipment")),
                   _scale(table.life_support_usd_per_kg, get("life_support")),
                   _scale(table.comfort_usd_per_kg, get("comfort")))
    lander = _scale(table.lander_usd_per_kg, get("power_system") + get("structure") + get("margin"))
    return CostEstimate(
        trajectory=traj, mass_moon_kg=mass_moon, mass_ratio=ratio, mass_leo_kg=leo, site_factor=k_site,
        launches=launches_needed(leo, rocket), utilization=utilization(leo, rocket),
        flight_time_days=tuple(TRAJECTORIES[traj]["duration_days"]),
        launch_usd=launch, payload_usd=payload, lander_usd=lander, total_usd=_add(launch, payload, lander),
    )
