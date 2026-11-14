"""Профілі місії «безпілотна» і «пілотована» (задача M17, PROPOSALS П-6, VISION «Профілі місії»).

Профіль — набір **початкових значень**, а не заборона: будь-яке значення користувач може перевизначити,
і явний вибір завжди переважає профіль. Числові пороги профілю **не вигадуються**: вони беруться з
опублікованих джерел (`app/data/mission_thresholds.json`, задача D5) і передаються в `resolve` рядками
цього файлу, тож ядро не читає файли. Єдині значення, що задані тут, — порядок пріоритетів за
замовчуванням і мінімальна кількість екіпажу; обидва позначені ⚠️ як продуктові (не опубліковані) і
перевизначаються.

Чисті функції без Flask. Поле `from_profile` у результаті перелічує значення, яких користувач
не вказував, а задав профіль: інтерфейс (F11) підсвічує їх, щоб було видно, що це не вибір користувача.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from app.core import site_score
from app.core.payload import MAX_CREW
from app.core.site_score import Requirements

PROFILES = ("uncrewed", "crewed")

# ⚠️ Продуктові значення за замовчуванням (не з публікацій): для пілотованої місії першою ставимо радіацію,
# бо саме для неї NASA-STD-3001 задає дозові ліміти; безпілотна — енергія й зв'язок, як і без профілю.
DEFAULT_PRIORITIES: dict[str, tuple[str, ...]] = {
    "uncrewed": ("energy", "comms"),
    "crewed": ("radiation", "comms", "energy"),
}
MIN_CREW_CREWED_DEFAULT = 1  # ⚠️ мінімум для пілотованої місії; реальну кількість задає користувач

COMPARISONS = ("<", "<=", ">", ">=")
# Скільки відсотків становить «частка часу» в порогах D5 → частка в [0, 1]
_PERCENT_UNITS = {"%"}


@dataclass(frozen=True)
class Limit:
    """Допустиме значення: quantity <comparison> value; без значення — якісна вимога (як зв'язок «напряму з Землею»)."""

    quantity: str
    comparison: str | None
    value: float | None
    unit: str | None
    kind: str  # requirement — вимога документа; screening — фільтр відбору ділянок
    id: str  # id рядка в mission_thresholds.json; "override" — значення задав користувач
    scope: str = ""

    def to_dict(self) -> dict:
        return {"quantity": self.quantity, "comparison": self.comparison, "value": self.value,
                "unit": self.unit, "kind": self.kind, "id": self.id, "scope": self.scope}


@dataclass(frozen=True)
class ResolvedProfile:
    profile: str
    crew: int
    priorities: tuple[str, ...]
    limits: Mapping[str, Limit]
    life_support_enabled: bool
    comfort_enabled: bool
    from_profile: tuple[str, ...] = field(default_factory=tuple)  # поля, значення яких задав профіль

    def limit(self, quantity: str) -> Limit | None:
        return self.limits.get(quantity)

    def requirements(self, period_h: float | None = None) -> Requirements:
        """Вимоги до місця посадки з порогів профілю (M23; `period_h` лишено для сумісності, не потрібен).

        - `landing_slope_deg` (вимога документа, Artemis III: < 10°) → **жорстка** `max_slope_deg`;
        - `earth_visible_fraction` (фільтр відбору: ≥ 25 %) → **м'яка** `min_earth_fraction`;
        - `sun_visible_fraction` (фільтр відбору: ≥ 5 %) → **м'яка** `min_sun_fraction`.
        Для безпілотної порогів немає (у документах NASA вони лише для пілотованої), тож і вимог немає — користувач
        задає їх сам. `min_comm_hours` не задається: числового порогу зв'язку в знайдених документах немає (D5).
        """
        def threshold(quantity: str, upper: bool) -> float | None:
            lim = self.limits.get(quantity)
            if lim is None or lim.value is None:
                return None
            if lim.comparison not in (("<", "<=") if upper else (">", ">=")):
                return None
            return _fraction(lim) if quantity.endswith("_fraction") else float(lim.value)

        return Requirements(
            max_slope_deg=threshold("landing_slope_deg", upper=True),
            min_earth_fraction=threshold("earth_visible_fraction", upper=False),
            min_sun_fraction=threshold("sun_visible_fraction", upper=False),
        )

    def to_dict(self) -> dict:
        return {
            "profile": self.profile, "crew": self.crew, "priorities": list(self.priorities),
            "limits": {q: lim.to_dict() for q, lim in self.limits.items()},
            "categories": {"life_support": self.life_support_enabled, "comfort": self.comfort_enabled},
            "from_profile": list(self.from_profile),
        }


def _fraction(limit: Limit) -> float:
    assert limit.value is not None
    return limit.value / 100.0 if limit.unit in _PERCENT_UNITS else float(limit.value)


def _limits_for(profile: str, thresholds: Iterable[Mapping]) -> dict[str, Limit]:
    out: dict[str, Limit] = {}
    for row in thresholds:
        if row["profile"] not in (profile, "any"):
            continue
        if row["quantity"] in out:
            raise ValueError(f"Для профілю {profile} два пороги величини {row['quantity']}")
        out[row["quantity"]] = Limit(
            quantity=row["quantity"], comparison=row.get("comparison"), value=row.get("value"),
            unit=row.get("unit"), kind=row["kind"], id=row["id"], scope=row.get("scope", ""))
    return out


def resolve(profile: str, thresholds: Iterable[Mapping], *, crew: int | None = None,
            priorities: Iterable[str] | None = None,
            limit_overrides: Mapping[str, float | None] | None = None) -> ResolvedProfile:
    """Збирає профіль: пороги з джерел + пріоритети за замовчуванням, поверх яких — явні значення користувача.

    - `crew`: безпілотна — лише 0 (або не вказано); пілотована — від 1 до `payload.MAX_CREW` (не вказано → мінімум ⚠️);
    - `priorities`: явний порядок факторів переважає порядок профілю;
    - `limit_overrides`: `{величина: нове значення}` (порівняння лишається з порогу; `None` — прибрати поріг);
      величина без порогу в профілі додається лише якщо відомо порівняння — тут не допускається (ValueError).
    """
    if profile not in PROFILES:
        raise ValueError(f"Невідомий профіль {profile!r}; допустимо: {', '.join(PROFILES)}")
    from_profile: list[str] = []

    if crew is None:
        crew_value = 0 if profile == "uncrewed" else MIN_CREW_CREWED_DEFAULT
        if profile == "crewed":
            from_profile.append("crew")
    else:
        if isinstance(crew, bool) or not isinstance(crew, int):
            raise ValueError("crew має бути цілим числом")
        crew_value = crew
    if profile == "uncrewed" and crew_value != 0:
        raise ValueError("Безпілотна місія не має екіпажу: crew має бути 0")
    if profile == "crewed" and not 1 <= crew_value <= MAX_CREW:
        raise ValueError(f"Пілотована місія: crew від 1 до {MAX_CREW}")

    if priorities is None:
        prios = DEFAULT_PRIORITIES[profile]
        from_profile.append("priorities")
    else:
        prios = tuple(priorities)
        bad = [p for p in prios if p not in site_score.FACTORS]
        if bad or len(set(prios)) != len(prios):
            raise ValueError(f"priorities: невідомі або повторені фактори {bad or list(prios)}")

    limits = _limits_for(profile, thresholds)
    from_profile.extend(f"limits.{q}" for q in limits)
    for quantity, value in (limit_overrides or {}).items():
        if quantity not in limits:
            raise ValueError(f"Профіль {profile} не має порогу {quantity}: перевизначати нічого")
        if f"limits.{quantity}" in from_profile:
            from_profile.remove(f"limits.{quantity}")
        if value is None:
            del limits[quantity]
            continue
        old = limits[quantity]
        if old.comparison is None:
            raise ValueError(f"{quantity}: якісна вимога без числового порогу, число не задається")
        limits[quantity] = Limit(quantity, old.comparison, float(value), old.unit, old.kind, "override", old.scope)

    return ResolvedProfile(
        profile=profile, crew=crew_value, priorities=prios, limits=limits,
        life_support_enabled=crew_value > 0, comfort_enabled=crew_value > 0,
        from_profile=tuple(from_profile))
