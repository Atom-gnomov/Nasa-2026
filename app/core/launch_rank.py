"""Ранжування майданчиків і ракет для польоту до вибраної точки Місяця (docs/MATH.md, §21.7; задача M20).

Для кожного кандидата «майданчик × ракета × траєкторія» рахуємо вектор показників:
    Δv_заг   — TLI + гальмування біля Місяця (transfer.py, M10) + добавка майданчика (втрата прибавки від обертання
               Землі й доворот площини, launch.py, M19);
    m_НОО    — маса на НОО за Ціолковським (cost.py, M13) з Δv_TLI переходу й довороту площини та поправкою на широту;
    T        — тривалість перельоту; W — вікна запуску на добу;
    C, p     — вартість запуску й ризик (діапазони; cost.py, risk.py).
Фактори оцінки (0…1, «більше — краще»): fuel (m_НОО), speed (T), windows (W), cost (C), risk (p); ваги — за порядком
пріоритетів (ROC), режими weighted / maximin, множина Парето — як у §19 (site_score.py).

Що бракує в каталогах, позначаємо, а не вигадуємо: ціни запуску й імовірності відмови беремо з «типової ракети» M13/M14
(`provisional`), проєктні ракети (`verified_by_flight: false`) позначені. Ракета, що не вміщує масу, — недопустима
(`fits: false`), але лишається в результаті з поясненням. Чисті функції без Flask: рядки каталогів — словники.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace

import numpy as np

from app.core import cost, risk, scoring
from app.core.launch import best_inclination_deg, site_departure

FACTORS = ("fuel", "speed", "windows", "cost", "risk")
MODES = ("weighted", "maximin")
Range = tuple[float, float]


@dataclass(frozen=True)
class Candidate:
    """Майданчик × ракета (або система запуску з D6)."""

    site_id: str
    site_name: str
    site_kind: str
    lat: float
    lon: float
    vehicle_id: str
    vehicle_name: str
    catalog: str  # "rockets" (D7) | "launch_systems" (D6)
    status: str | None  # active · in_testing · design_target · retired; None — невідомо
    verified_by_flight: bool | None
    capacity_leo_kg: float | None
    capacity_tli_kg: float | None
    price_usd_per_kg_lunar_surface: float | None = None


@dataclass
class LaunchOption:
    candidate: Candidate
    trajectory: str
    inclination_deg: float
    windows_per_day: int
    inertial_azimuths_deg: tuple[float, ...]
    dv_tli_m_s: Range | None
    dv_loi_m_s: Range | None
    dv_site_penalty_m_s: float
    dv_total_m_s: Range
    duration_days: Range
    mass_leo_kg: float
    capacity_basis: str  # "tli" | "leo"
    utilization: float
    launches: int
    fits: bool
    fit_note: str | None
    launch_cost_usd: Range
    risk_p: float
    risk_range: Range
    risk_band: str
    provisional_fields: tuple[str, ...]
    factors: dict[str, float] = field(default_factory=dict)
    score_pct: float = 0.0
    rank: int = 0
    pareto: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


# --- кандидати з каталогів ---------------------------------------------------------------------------------------


def _fact(row: Mapping, quantity: str) -> float | None:
    for f in row.get("facts", ()):
        if f.get("quantity") == quantity and isinstance(f.get("value"), (int, float)):
            return float(f["value"])
    return None


def candidates(launch_sites: Sequence[Mapping], rockets: Sequence[Mapping] = (),
               launch_systems: Sequence[Mapping] = (), include_design_targets: bool = True,
               include_inactive: bool = False) -> tuple[list[Candidate], list[dict]]:
    """Пари «майданчик × ракета» з каталогів (D6 launch_sites/launch_systems, D7 rockets).

    Повертає (кандидати, виключені з причиною). Ракета без відомого майданчика чи без місткості — виключена.
    """
    sites = {s["id"]: s for s in launch_sites}
    out: list[Candidate] = []
    excluded: list[dict] = []

    def add(row: Mapping, catalog: str, status: str | None, verified: bool | None) -> None:
        cap_leo, cap_tli = _fact(row, "capacity_leo_kg"), _fact(row, "capacity_tli_kg")
        if cap_leo is None and cap_tli is None:
            excluded.append({"vehicle_id": row["id"], "reason": "немає місткості на НОО чи TLI в каталозі"})
            return
        site_ids = [s for s in row.get("launch_site_ids", ()) if s in sites]
        if not site_ids:
            excluded.append({"vehicle_id": row["id"], "reason": "майданчика немає в каталозі стартів"})
            return
        for sid in site_ids:
            s = sites[sid]
            out.append(Candidate(
                site_id=sid, site_name=s["name"], site_kind=s.get("kind", "spaceport"), lat=float(s["lat"]),
                lon=float(s["lon"]), vehicle_id=row["id"], vehicle_name=row["name"], catalog=catalog, status=status,
                verified_by_flight=verified, capacity_leo_kg=cap_leo, capacity_tli_kg=cap_tli,
                price_usd_per_kg_lunar_surface=_fact(row, "price_usd_per_kg_lunar_surface"),
            ))

    for r in rockets:
        if r.get("status") == "retired" and not include_inactive:
            excluded.append({"vehicle_id": r["id"], "reason": "знята з експлуатації"})
        elif r.get("status") in ("design_target", "in_testing") and not include_design_targets:
            excluded.append({"vehicle_id": r["id"], "reason": "проєктна ціль або випробування — вимкнено фільтром"})
        else:
            add(r, "rockets", r.get("status"), r.get("verified_by_flight"))
    for s in launch_systems:
        active = s.get("active")
        if active is False and not include_inactive:
            excluded.append({"vehicle_id": s["id"], "reason": "система запуску не діє"})
            continue
        status = "active" if active else ("retired" if active is False else None)
        add(s, "launch_systems", status, None if active is None else bool(active))
    return out, excluded


# --- оцінка одного кандидата ---------------------------------------------------------------------------------------


def _get(obj, name):
    return obj[name] if isinstance(obj, Mapping) else getattr(obj, name)


def evaluate(cand: Candidate, transfer_option, moon_declination_deg: float, mass_moon_kg: float,
             allow_multiple_launches: bool = False, rocket_fallback: cost.Rocket = cost.DEFAULT_ROCKET,
             risk_params: risk.RiskParams = risk.DEFAULT_PARAMS) -> LaunchOption:
    """Показники для кандидата й варіанта переходу (TransferOption з transfer.py або словник з тими ж полями)."""
    if mass_moon_kg <= 0:
        raise ValueError("Маса на Місяці має бути додатною")
    trajectory = _get(transfer_option, "trajectory")
    inc = best_inclination_deg(cand.lat, moon_declination_deg)
    dep = site_departure(cand.lat, inc)

    dv_tli = _get(transfer_option, "dv_tli_m_s")
    dv_loi = _get(transfer_option, "dv_loi_m_s")
    dv_total = _get(transfer_option, "dv_total_m_s")
    best = _get(transfer_option, "best")
    base = cost.DEFAULT_TRANSFER
    tli_for_mass = _get(best, "dv_tli_m_s") if best is not None else base.dv_tli_m_s
    params = replace(base, dv_tli_m_s=tli_for_mass + dep.plane_change_dv_m_s)
    k_site = cost.site_factor(cand.lat, params)
    mass_leo = cost.mass_leo(mass_moon_kg, trajectory, params) * k_site

    # місткість: якщо відома на TLI — ракета сама розганяє до Місяця, порівнюємо масу після TLI
    if cand.capacity_tli_kg:
        mass_after_tli = cost.mass_leo(mass_moon_kg, trajectory, replace(params, dv_tli_m_s=0.0))
        u, basis = mass_after_tli / cand.capacity_tli_kg, "tli"
    else:
        u, basis = mass_leo / cand.capacity_leo_kg, "leo"
    launches = max(1, math.ceil(u - 1e-12))
    fits = u <= 1.0
    note = None
    if not fits:
        if cand.site_kind == "air_launch":
            note = "маса не вміщується в ракету з літака-носія; потрібна більша ракета"
        elif basis == "tli":
            note = "маса після TLI більша за місткість ракети на TLI; потрібно кілька пусків і стикування"
        else:
            note = "один пуск не вистачає: потрібно кілька пусків і стикування на орбіті"
    feasible_launch = fits or (allow_multiple_launches and cand.site_kind != "air_launch")

    provisional: list[str] = []
    if cand.price_usd_per_kg_lunar_surface:  # ціна послуги доставки на поверхню (Starship) — за масу на Місяці
        launch_cost = (cand.price_usd_per_kg_lunar_surface * mass_moon_kg,) * 2
    else:
        price = rocket_fallback.price_usd_per_kg
        launch_cost = (price[0] * mass_leo, price[1] * mass_leo)
        provisional.append("price_usd_per_kg")
    p_launch, _ = risk.launch_risk(u, risk_params)
    provisional.append("failure_probability")
    p = 1.0 - (1.0 - p_launch) * (1.0 - risk_params.p_transit[trajectory])
    p_range = (min(1.0, p * risk_params.uncertainty[0]), min(1.0, p * risk_params.uncertainty[1]))

    penalty = dep.dv_penalty_m_s
    return LaunchOption(
        candidate=cand, trajectory=trajectory, inclination_deg=inc, windows_per_day=dep.windows_per_day,
        inertial_azimuths_deg=dep.inertial_azimuths_deg,
        dv_tli_m_s=None if dv_tli is None else tuple(dv_tli),
        dv_loi_m_s=None if dv_loi is None else tuple(dv_loi),
        dv_site_penalty_m_s=penalty,
        dv_total_m_s=(dv_total[0] + penalty, dv_total[1] + penalty),
        duration_days=tuple(_get(transfer_option, "duration_days")),
        mass_leo_kg=mass_leo, capacity_basis=basis, utilization=u, launches=launches,
        fits=bool(feasible_launch), fit_note=note, launch_cost_usd=launch_cost,
        risk_p=p, risk_range=p_range, risk_band=risk.band(p), provisional_fields=tuple(provisional),
    )


# --- ранжування ------------------------------------------------------------------------------------------------


def _raw(option: LaunchOption, factor: str) -> float:
    if factor == "fuel":
        return option.mass_leo_kg
    if factor == "speed":
        return sum(option.duration_days) / 2
    if factor == "windows":
        return float(option.windows_per_day)
    if factor == "cost":
        return sum(option.launch_cost_usd) / 2
    if factor == "risk":
        return option.risk_p
    raise ValueError(f"Невідомий фактор: {factor}")


def rank(options: Sequence[LaunchOption], priorities: Sequence[str] = FACTORS,
         mode: str = "weighted") -> list[LaunchOption]:
    """Оцінки факторів (мін-макс серед кандидатів; вікна — за абсолютною шкалою 0…2), бал, Парето, ранг.

    Порядок: допустимі (вміщуються) перед недопустимими; далі бал, найгірший фактор, назва — детерміновано.
    """
    if mode not in MODES:
        raise ValueError(f"Невідомий режим: {mode}")
    if not priorities or any(f not in FACTORS for f in priorities) or len(set(priorities)) != len(priorities):
        raise ValueError(f"Пріоритети — унікальні фактори з {', '.join(FACTORS)}")
    opts = list(options)
    if not opts:
        return []
    weights = scoring.roc_weights(len(priorities))
    for f in priorities:
        raw = np.array([_raw(o, f) for o in opts])
        scores = np.clip(raw / 2.0, 0.0, 1.0) if f == "windows" else scoring.normalize(raw, higher_is_better=False)
        for o, s in zip(opts, scores, strict=True):
            o.factors[f] = round(float(s), 4)
    for o in opts:
        vec = np.array([o.factors[f] for f in priorities])
        o.score_pct = round(float(100.0 * (vec @ weights if mode == "weighted" else vec.min())), 2)
    feasible = [o for o in opts if o.fits]
    if feasible:
        matrix = np.array([[o.factors[f] for f in priorities] for o in feasible])
        for k in scoring.pareto_front(matrix):
            feasible[int(k)].pareto = True
    opts.sort(key=lambda o: (not o.fits, -o.score_pct, -min(o.factors.values()),
                             o.candidate.site_id, o.candidate.vehicle_id, o.trajectory))
    for i, o in enumerate(opts, start=1):
        o.rank = i
    return opts


def rank_launches(launch_sites: Sequence[Mapping], transfer_options: Mapping[str, object], mass_moon_kg: float,
                  rockets: Sequence[Mapping] = (), launch_systems: Sequence[Mapping] = (),
                  moon_declination_deg: float | None = None, trajectories: Sequence[str] = ("direct", "low_energy"),
                  priorities: Sequence[str] = FACTORS, mode: str = "weighted", include_design_targets: bool = True,
                  allow_multiple_launches: bool = False) -> dict:
    """Повний розрахунок §21.7: кандидати → показники → рейтинг.

    transfer_options — результат transfer.transfer_options() (ключі — траєкторії). Схилення Місяця, якщо не задане,
    береться з найкращого прямого переходу (`min_parking_inclination_deg`).
    """
    if moon_declination_deg is None:
        best = _get(transfer_options["direct"], "best")
        moon_declination_deg = _get(best, "min_parking_inclination_deg")
    cands, excluded = candidates(launch_sites, rockets, launch_systems, include_design_targets)
    options = [evaluate(c, transfer_options[t], moon_declination_deg, mass_moon_kg, allow_multiple_launches)
               for c in cands for t in trajectories]
    ranked = rank(options, priorities, mode)
    return {"options": ranked, "excluded": excluded, "moon_declination_deg": float(moon_declination_deg),
            "priorities": list(priorities), "mode": mode}
