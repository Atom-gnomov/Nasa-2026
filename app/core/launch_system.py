"""Система запуску: ракета + спосіб старту (задача M18, PROPOSALS П-10, MATH §13 і §20).

Замість «типової ракети» в моделі вартості й ризику (`cost.py`, `risk.py`) беремо систему з каталогу
`app/data/launch_systems.json` (задача D6). Каталог містить лише те, що є в джерелах: місткість на НОО,
висоту скидання, літак-носій. **Ціни за кг і ймовірності відмови в каталозі немає** (їх чекає D4/D7),
тому для них лишається тимчасове значення «типової ракети», а в результаті прямо перелічено, які
поля тимчасові (`provisional_fields`) — користувач не вважатиме їх даними про цю ракету.

Чисті функції без Flask: рядок каталогу приходить словником.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

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

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "kind": self.kind, "active": self.active,
            "capacity_leo_kg": self.capacity_leo_kg, "capacity_condition": self.capacity_condition,
            "drop_altitude_m": self.drop_altitude_m, "launch_site_ids": list(self.launch_site_ids),
        }


def _fact(row: Mapping, quantity: str) -> Mapping | None:
    return next((f for f in row.get("facts", ()) if f.get("quantity") == quantity), None)


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
    )


@dataclass(frozen=True)
class RocketChoice:
    """Ракета для `cost.py` / `risk.py` і перелік тимчасових полів, яких каталог не містить."""

    rocket: Rocket
    system: LaunchSystem
    provisional_fields: tuple[str, ...]

    def to_dict(self) -> dict:
        return {"system": self.system.to_dict(), "provisional_fields": list(self.provisional_fields),
                "rocket": {"name": self.rocket.name, "capacity_leo_kg": self.rocket.capacity_leo_kg,
                           "price_usd_per_kg": list(self.rocket.price_usd_per_kg),
                           "failure_probability": self.rocket.failure_probability}}


def to_rocket(system: LaunchSystem, price_usd_per_kg: Range | None = None,
              failure_probability: float | None = None, fallback: Rocket = DEFAULT_ROCKET) -> RocketChoice:
    """Система запуску → `Rocket`: місткість з каталогу; ціна й відмова — задані явно або тимчасові з `fallback`.

    Без місткості на НОО в каталозі система непридатна (ValueError): вигадувати її не можна.
    """
    if system.capacity_leo_kg is None:
        raise ValueError(f"{system.name}: у каталозі немає місткості на НОО (є лише для інших орбіт)")
    if system.capacity_leo_kg <= 0:
        raise ValueError(f"{system.name}: місткість має бути додатною")
    provisional = []
    if price_usd_per_kg is None:
        price_usd_per_kg = fallback.price_usd_per_kg
        provisional.append("price_usd_per_kg")
    if failure_probability is None:
        failure_probability = fallback.failure_probability
        provisional.append("failure_probability")
    rocket = Rocket(name=system.name, capacity_leo_kg=system.capacity_leo_kg,
                    price_usd_per_kg=price_usd_per_kg, failure_probability=failure_probability)
    return RocketChoice(rocket=rocket, system=system, provisional_fields=tuple(provisional))


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
