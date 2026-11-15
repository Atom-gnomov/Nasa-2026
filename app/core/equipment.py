"""Обладнання з каталогу NASA для категорії «Обладнання» (П-14): суми мас, потужності й ціна доставки за позиціями.

Чисті функції без Flask. Каталог — app/data/equipment_catalog.json (маса й потужність кожної позиції з документів
NASA, з цитатами). Власної ціни позиції джерела не дають, тому гроші — доставка на Місяць за оцінкою NASA OIG
(діапазон $/кг):
вартість = маса · ціна кілограма. ⚠️ Це лише доставка, не розробка й виготовлення обладнання.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

MAX_ITEMS = 12  # різних позицій у запиті
MAX_COUNT = 50  # штук однієї позиції


def parse_items(raw: object, catalog: Mapping) -> list[tuple[Mapping, int]]:
    """Список {id, count} із запиту → [(позиція каталогу, кількість)]. ValueError — помилка даних; count 0 пропуск."""
    if raw is None:
        return []
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) > MAX_ITEMS:
        raise ValueError(f"equipment_items має бути списком не довше {MAX_ITEMS} позицій")
    by_id = {item["id"]: item for item in catalog["items"]}
    out: list[tuple[Mapping, int]] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, Mapping) or set(entry) - {"id", "count"}:
            raise ValueError("Кожна позиція equipment_items — об'єкт {id, count}")
        item_id, count = entry.get("id"), entry.get("count", 1)
        if item_id not in by_id:
            raise ValueError(f"Невідома позиція обладнання: {item_id} (є {', '.join(by_id)})")
        if item_id in seen:
            raise ValueError(f"Позиція {item_id} вказана двічі")
        if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= MAX_COUNT:
            raise ValueError(f"count має бути цілим від 0 до {MAX_COUNT}")
        seen.add(item_id)
        if count:
            out.append((by_id[item_id], count))
    return out


def summarize(items: Sequence[tuple[Mapping, int]], delivery_usd_per_kg: Sequence[float]) -> dict:
    """Підсумок за позиціями: маса (діапазон і середнє), споживання (пік), потужність, яку дають, доставка на Місяць."""
    d_lo, d_hi = delivery_usd_per_kg
    rows = []
    mass_lo = mass_hi = power = supply = 0.0
    for item, count in items:
        lo, hi = item["mass_kg"][0] * count, item["mass_kg"][1] * count
        peak = (item["power_w"][1] * count) if item["power_w"] else None
        give = (item["supply_power_w"] * count) if item["supply_power_w"] else None
        rows.append({
            "id": item["id"], "name": item["name"], "count": count, "mass_kg": [lo, hi], "power_w": peak,
            "supply_power_w": give, "delivery_usd": [lo * d_lo, hi * d_hi], "source": item["source"],
        })
        mass_lo += lo
        mass_hi += hi
        power += peak or 0.0
        supply += give or 0.0
    return {
        "items": rows,
        "mass_kg": (mass_lo + mass_hi) / 2.0,  # середнє — точкова оцінка для бюджету
        "mass_range_kg": [mass_lo, mass_hi],
        "power_w": power,
        "supply_power_w": supply,
        "delivery_usd": [mass_lo * d_lo, mass_hi * d_hi],
        "delivery_usd_per_kg": [d_lo, d_hi],
    }
