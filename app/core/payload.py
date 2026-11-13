"""Модель маси корисного навантаження (docs/MATH.md, §20; VISION: «Корисне навантаження й вартість»).

Користувач вибирає розмір трьох категорій — обладнання, життєзабезпечення, умови й зручності — рівнями
Мінімум · Базовий · Розширений · Максимум (або числом 0…1). Модель повертає маси, споживану потужність і тепло;
панелі, акумулятори, конструкція й запас маси рахуються автоматично (замкнена формула, ітерація не потрібна:
панелі й акумулятори пасивні й не збільшують споживання).

⚠️ УСІ ЧИСЛА В PayloadParams — ТИМЧАСОВІ ОРІЄНТОВНІ ЗНАЧЕННЯ для налаштування, а не дані з джерел. Реальні маси
й ціни блоків чекають задачі D4 (відкрите питання VISION); тому результат завжди супроводжується діапазоном
`total_range_kg`, а не одним числом. Чисті функції без Flask.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass

CATEGORIES = ("equipment", "life_support", "comfort")
LEVELS = {"min": 0.0, "basic": 1.0 / 3.0, "extended": 2.0 / 3.0, "max": 1.0}
MAX_CREW = 6
MAX_DAYS = 365.0

Pair = tuple[float, float]  # (значення при розмірі 0, значення при розмірі 1) — лінійна інтерполяція


@dataclass(frozen=True)
class PayloadParams:
    """⚠️ Тимчасові значення (див. модуль). Кожна пара — від рівня «Мінімум» до «Максимум»."""

    equipment_mass_kg: Pair = (30.0, 1500.0)  # прилади, зв'язок, ровер, буровий комплекс
    equipment_power_w: Pair = (20.0, 800.0)
    consumables_kg_per_person_day: Pair = (5.0, 2.0)  # вищий рівень регенерації → менше витратних
    ls_fixed_kg_per_person: Pair = (150.0, 600.0)  # обладнання життєзабезпечення на людину
    ls_shield_kg: Pair = (0.0, 400.0)  # захист від радіації, на весь екіпаж
    ls_power_w_per_person: Pair = (300.0, 1000.0)
    comfort_volume_m3_per_person: Pair = (2.0, 12.0)  # житловий об'єм на людину
    habitat_kg_per_m3: float = 40.0  # маса оболонки на м³
    comfort_kg_per_person_day: Pair = (0.5, 2.0)  # гігієна, одяг, дозвілля
    comfort_power_w_per_person: Pair = (50.0, 300.0)
    panel_w_per_kg: float = 60.0  # питома потужність панелей із розгортанням
    battery_wh_per_kg: float = 150.0
    battery_depth_of_discharge: float = 0.8
    structure_fraction: float = 0.25  # конструкція модуля — частка від суми корисного навантаження й енергетики
    margin_fraction: float = 0.20  # запас маси
    uncertainty: Pair = (0.75, 1.35)  # діапазон мін–макс навколо оцінки (ціни й маси орієнтовні)


DEFAULT_PARAMS = PayloadParams()


@dataclass(frozen=True)
class PayloadBudget:
    sizes: dict[str, float]
    crew: int
    days: float
    masses_kg: dict[str, float]  # equipment, life_support, comfort, power_system, structure, margin
    power_w: float  # постійне споживання категорій
    heat_w: float  # майже вся електрична потужність стає теплом
    panel_kg: float
    battery_kg: float
    payload_kg: float  # лише три категорії
    total_kg: float  # усе, що сідає на Місяць
    total_range_kg: tuple[float, float]

    def to_dict(self) -> dict:
        return asdict(self)


def size_from_level(level: str | float) -> float:
    """Рівень «min» / «basic» / «extended» / «max» або число 0…1 → розмір s ∈ [0, 1]."""
    if isinstance(level, str):
        if level not in LEVELS:
            raise ValueError(f"Невідомий рівень: {level} (є {', '.join(LEVELS)})")
        return LEVELS[level]
    if isinstance(level, bool) or not isinstance(level, (int, float)) or not 0.0 <= level <= 1.0:
        raise ValueError("Розмір має бути числом від 0 до 1 або рівнем")
    return float(level)


def _lerp(pair: Pair, s: float) -> float:
    return pair[0] + (pair[1] - pair[0]) * s


def _sizes(sizes: Mapping[str, str | float] | None) -> dict[str, float]:
    sizes = dict(sizes or {})
    unknown = set(sizes) - set(CATEGORIES)
    if unknown:
        raise ValueError(f"Невідомі категорії: {', '.join(sorted(unknown))}")
    return {c: size_from_level(sizes.get(c, "basic")) for c in CATEGORIES}


def payload_budget(sizes: Mapping[str, str | float] | None = None, crew: int = 0, days: float = 0.0,
                   longest_night_h: float = 0.0, params: PayloadParams = DEFAULT_PARAMS) -> PayloadBudget:
    """Маса, потужність і тепло корисного навантаження.

    sizes — розмір категорій (за замовчуванням «basic»); crew — людей (0 — безпілотна: життєзабезпечення й
    зручності = 0); days — тривалість перебування, діб; longest_night_h — найдовша ніч (годин), під яку
    підбираються акумулятори (0 — без акумуляторів).
    """
    s = _sizes(sizes)
    if isinstance(crew, bool) or not isinstance(crew, int) or not 0 <= crew <= MAX_CREW:
        raise ValueError(f"crew має бути цілим від 0 до {MAX_CREW}")
    if not 0.0 <= days <= MAX_DAYS:
        raise ValueError(f"days має бути в межах 0…{MAX_DAYS:g}")
    if longest_night_h < 0:
        raise ValueError("longest_night_h не може бути від'ємним")

    equipment = _lerp(params.equipment_mass_kg, s["equipment"])
    life_support = comfort = 0.0
    power = _lerp(params.equipment_power_w, s["equipment"])
    if crew > 0:
        ls, cf = s["life_support"], s["comfort"]
        life_support = (crew * days * _lerp(params.consumables_kg_per_person_day, ls)
                        + crew * _lerp(params.ls_fixed_kg_per_person, ls)
                        + _lerp(params.ls_shield_kg, ls))
        comfort = (crew * _lerp(params.comfort_volume_m3_per_person, cf) * params.habitat_kg_per_m3
                   + crew * days * _lerp(params.comfort_kg_per_person_day, cf))
        power += crew * (_lerp(params.ls_power_w_per_person, ls) + _lerp(params.comfort_power_w_per_person, cf))

    panel = power / params.panel_w_per_kg
    battery = power * longest_night_h / (params.battery_wh_per_kg * params.battery_depth_of_discharge)
    payload = equipment + life_support + comfort
    subtotal = payload + panel + battery
    structure = params.structure_fraction * subtotal
    margin = params.margin_fraction * (subtotal + structure)
    total = subtotal + structure + margin
    lo, hi = params.uncertainty
    return PayloadBudget(
        sizes=s, crew=crew, days=float(days),
        masses_kg={"equipment": equipment, "life_support": life_support, "comfort": comfort,
                   "power_system": panel + battery, "structure": structure, "margin": margin},
        power_w=power, heat_w=power, panel_kg=panel, battery_kg=battery,
        payload_kg=payload, total_kg=total, total_range_kg=(total * lo, total * hi),
    )
