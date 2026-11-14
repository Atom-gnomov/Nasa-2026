"""Система запуску: ракета + спосіб старту (задача M18, PROPOSALS П-10, MATH §13 і §20).

Замість «типової ракети» в моделі вартості й ризику (`cost.py`, `risk.py`) беремо систему з каталогу
`app/data/launch_systems.json` (задача D6) або `rockets.json` (D7). Каталог містить лише те, що є в джерелах:
місткість на НОО, висоту скидання, літак-носій і — після задачі D8 — **ціну за кг** (`price_usd_per_kg_leo_min`
/ `_max`) та **статистику польотів** (`flights_total`, `flights_failed`). Ймовірність відмови з неї — за правилом
спадкоємності Лапласа `(невдалих + 1) / (усього + 2)` з діапазоном Вілсона 90 % (MATH §20). Чого в каталозі
немає, для того лишається тимчасове значення «типової ракети», а `provisional_fields` прямо перелічує, які поля
тимчасові (M21: після D8 список скорочується сам) — користувач не вважатиме їх даними про цю ракету.

Чисті функції без Flask: рядок каталогу приходить словником.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from dataclasses import replace

from app.core import risk
from app.core.cost import DEFAULT_ROCKET, Range, Rocket

KINDS = ("spaceport", "sea_platform", "air_launch")


@dataclass(frozen=True)
class LaunchSystem:
    id: str
    name: str
    kind: str  # spaceport · sea_platform · air_launch
    active: bool | None  # None — стан не підтверджено
    capacity_leo_kg: float | None  # None — у каталозі немає місткості на НОО
    capacity_condition: str | None  # для якої орбіти й умови значення місткості (з каталогу)
    drop_altitude_m: float | None  # лише повітряний старт
    launch_site_ids: tuple[str, ...]
    price_usd_per_kg: Range | None = None  # D8: ціна за кг на НОО, діапазон; None — немає в каталозі
    flights_total: int | None = None  # D8: усього польотів
    flights_failed: int | None = None  # D8: з них невдалих

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "kind": self.kind, "active": self.active,
            "capacity_leo_kg": self.capacity_leo_kg, "capacity_condition": self.capacity_condition,
            "drop_altitude_m": self.drop_altitude_m, "launch_site_ids": list(self.launch_site_ids),
            "price_usd_per_kg_leo": None if self.price_usd_per_kg is None else list(self.price_usd_per_kg),
            "flights_total": self.flights_total, "flights_failed": self.flights_failed,
            "failure_probability": None if self.failure_estimate() is None else self.failure_estimate()[0],
        }

    def failure_estimate(self) -> tuple[float, Range] | None:
        """(ймовірність відмови, діапазон) зі статистики польотів каталогу; None — статистики немає."""
        if self.flights_total is None or self.flights_failed is None:
            return None
        return failure_from_flights(self.flights_total, self.flights_failed)


def _fact(row: Mapping, quantity: str) -> Mapping | None:
    return next((f for f in row.get("facts", ()) if f.get("quantity") == quantity), None)


def _int_fact(row: Mapping, quantity: str) -> int | None:
    fact = _fact(row, quantity)
    if fact is None or isinstance(fact["value"], bool) or not isinstance(fact["value"], (int, float)):
        return None
    value = fact["value"]
    if value < 0 or value != int(value):
        raise ValueError(f"{row.get('id')}: {quantity} має бути невід'ємним цілим, а не {value!r}")
    return int(value)


def failure_from_flights(flights_total: int, flights_failed: int, z: float = 1.645) -> tuple[float, Range]:
    """Ймовірність відмови за статистикою польотів і її діапазон.

    Точка — правило спадкоємності Лапласа `(f + 1) / (n + 2)`: навіть без невдач ймовірність не нуль, а мало польотів
    дають широкий діапазон. Діапазон — інтервал Вілсона (z = 1,645 → 90 %). `n = 0` — статистики немає (ValueError).
    """
    n, f = int(flights_total), int(flights_failed)
    if n < 1:
        raise ValueError("Статистики польотів немає (flights_total = 0)")
    if not 0 <= f <= n:
        raise ValueError("flights_failed має бути в межах 0…flights_total")
    p = (f + 1) / (n + 2)
    phat = f / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return p, (max(0.0, centre - half), min(1.0, centre + half))


def from_catalog(row: Mapping) -> LaunchSystem:
    """Рядок `launch_systems.json` → система запуску. Відсутні в джерелах величини лишаються `None`."""
    if row.get("kind") not in KINDS:
        raise ValueError(f"{row.get('id')}: невідомий спосіб старту {row.get('kind')!r}")
    capacity = _fact(row, "capacity_leo_kg")
    drop = _fact(row, "drop_altitude_m")
    return LaunchSystem(
        id=row["id"], name=row["name"], kind=row["kind"], active=row.get("active"),
        capacity_leo_kg=float(capacity["value"]) if capacity else None,
        capacity_condition=capacity.get("condition") if capacity else None,
        drop_altitude_m=float(drop["value"]) if drop else None,
        launch_site_ids=tuple(row.get("launch_site_ids", ())),
        price_usd_per_kg=_price(row),
        flights_total=_int_fact(row, "flights_total"), flights_failed=_int_fact(row, "flights_failed"),
    )


def _price(row: Mapping) -> Range | None:
    lo, hi = _fact(row, "price_usd_per_kg_leo_min"), _fact(row, "price_usd_per_kg_leo_max")
    if lo is None or hi is None:
        return None
    a, b = float(lo["value"]), float(hi["value"])
    if not 0 < a <= b:
        raise ValueError(f"{row.get('id')}: ціна за кг має бути 0 < мін ≤ макс")
    return (a, b)


@dataclass(frozen=True)
class RocketChoice:
    """Ракета для `cost.py` / `risk.py` і перелік тимчасових полів, яких каталог не містить."""

    rocket: Rocket
    system: LaunchSystem
    provisional_fields: tuple[str, ...]
    failure_range: Range | None = None  # діапазон відмови зі статистики польотів; None — тимчасове значення

    def risk_params(self, base: risk.RiskParams = risk.DEFAULT_PARAMS) -> risk.RiskParams:
        """Параметри ризику з базою відмови цієї ракети замість загальної (`p_launch_base`)."""
        return replace(base, p_launch_base=self.rocket.failure_probability)

    def to_dict(self) -> dict:
        return {"system": self.system.to_dict(), "provisional_fields": list(self.provisional_fields),
                "rocket": {"name": self.rocket.name, "capacity_leo_kg": self.rocket.capacity_leo_kg,
                           "price_usd_per_kg": list(self.rocket.price_usd_per_kg),
                           "failure_probability": self.rocket.failure_probability}}


def to_rocket(system: LaunchSystem, price_usd_per_kg: Range | None = None,
              failure_probability: float | None = None, fallback: Rocket = DEFAULT_ROCKET) -> RocketChoice:
    """Система запуску → `Rocket`: місткість з каталогу; ціна й відмова — явні, з каталогу (D8) або тимчасові.

    Пріоритет: явне значення аргумента → факти каталогу → `fallback` (тимчасове, потрапляє в `provisional_fields`).
    Без місткості на НОО в каталозі система непридатна (ValueError): вигадувати її не можна.
    """
    if system.capacity_leo_kg is None:
        raise ValueError(f"{system.name}: у каталозі немає місткості на НОО (є лише для інших орбіт)")
    if system.capacity_leo_kg <= 0:
        raise ValueError(f"{system.name}: місткість має бути додатною")
    provisional = []
    if price_usd_per_kg is None:
        if system.price_usd_per_kg is not None:
            price_usd_per_kg = system.price_usd_per_kg
        else:
            price_usd_per_kg = fallback.price_usd_per_kg
            provisional.append("price_usd_per_kg")
    failure_range = None
    if failure_probability is None:
        estimate = system.failure_estimate() if (system.flights_total or 0) >= 1 else None
        if estimate is not None:
            failure_probability, failure_range = estimate
        else:
            failure_probability = fallback.failure_probability
            provisional.append("failure_probability")
    rocket = Rocket(name=system.name, capacity_leo_kg=system.capacity_leo_kg,
                    price_usd_per_kg=price_usd_per_kg, failure_probability=failure_probability)
    return RocketChoice(rocket=rocket, system=system, provisional_fields=tuple(provisional),
                        failure_range=failure_range)


def fit(mass_leo_kg: float, system: LaunchSystem) -> dict:
    """Чи вміщується маса на НОО в систему: заповненість, кількість пусків і пояснення.

    Повітряний старт лише з заповненістю > 1 не збере місячний апарат докінця: стикування на орбіті для
    таких малих ракет нереалістичне, тому це окремо позначено в `note`.
    """
    if system.capacity_leo_kg is None:
        raise ValueError(f"{system.name}: у каталозі немає місткості на НОО")
    u = mass_leo_kg / system.capacity_leo_kg
    n = max(1, math.ceil(mass_leo_kg / system.capacity_leo_kg))
    note = None
    if u > 1.0 and system.kind == "air_launch":
        note = "маса не вміщується в ракету з літака-носія; потрібна більша ракета, а не кілька малих"
    elif u > 1.0:
        note = "один пуск не вистачає: потрібне кілька пусків і стикування на орбіті"
    return {"utilization": u, "launches": n, "fits_single_launch": u <= 1.0, "note": note}
