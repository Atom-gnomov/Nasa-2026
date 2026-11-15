"""Цілі місії (M25, П-14; docs/RESOURCES.md §11): мета задає типові вибори наступних кроків майстра.

Мета (збір зразків, пошук води й льоду, випробування технологій, наука, база) підставляє тип місії, тривалість
перебування й порядок пріоритетів «Підбору». Це **типові значення**, а не нормативи (⚠️ тимчасово): користувач їх
змінює. Чисті функції без Flask.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

PROFILES = ("uncrewed", "crewed")
FACTORS = ("energy", "comms", "radiation", "temperature")  # як у site_score.FACTORS
MAX_STAY_DAYS = 365


@dataclass(frozen=True)
class MissionGoal:
    id: str
    name: str
    name_en: str
    summary: str
    mission_profile: str
    stay_days: int
    priorities: tuple[str, ...]
    site_notes: tuple[str, ...]
    instrument_ids: tuple[str, ...]
    sources: tuple[Mapping[str, str], ...]

    def defaults(self) -> dict:
        """Що підставляє мета в наступні кроки: тип місії, тривалість перебування, пріоритети «Підбору»."""
        return {"mission_profile": self.mission_profile, "stay_days": self.stay_days,
                "priorities": list(self.priorities)}

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "name_en": self.name_en, "summary": self.summary,
                "defaults": self.defaults(), "site_notes": list(self.site_notes),
                "instrument_ids": list(self.instrument_ids), "sources": [dict(s) for s in self.sources]}


def parse_goal(row: Mapping) -> MissionGoal:
    """Ціль із запису каталогу; ValueError — помилка в даних."""
    profile = row.get("mission_profile")
    if profile not in PROFILES:
        raise ValueError(f"{row.get('id')}: mission_profile має бути {' або '.join(PROFILES)}")
    stay = row.get("stay_days")
    if isinstance(stay, bool) or not isinstance(stay, int) or not 1 <= stay <= MAX_STAY_DAYS:
        raise ValueError(f"{row.get('id')}: stay_days має бути цілим від 1 до {MAX_STAY_DAYS}")
    priorities = tuple(row.get("priorities") or ())
    if not priorities or any(p not in FACTORS for p in priorities) or len(set(priorities)) != len(priorities):
        raise ValueError(f"{row.get('id')}: priorities — унікальні фактори з {', '.join(FACTORS)}")
    if not row.get("sources"):
        raise ValueError(f"{row.get('id')}: потрібне джерело")
    return MissionGoal(id=row["id"], name=row["name"], name_en=row["name_en"], summary=row["summary"],
                       mission_profile=profile, stay_days=stay, priorities=priorities,
                       site_notes=tuple(row.get("site_notes") or ()),
                       instrument_ids=tuple(row.get("instrument_ids") or ()), sources=tuple(row["sources"]))


def load_goals(rows: Sequence[Mapping]) -> list[MissionGoal]:
    goals = [parse_goal(r) for r in rows]
    ids = [g.id for g in goals]
    if len(ids) != len(set(ids)):
        raise ValueError("Ідентифікатори цілей мають бути унікальними")
    return goals


def find_goal(goals: Sequence[MissionGoal], goal_id: str) -> MissionGoal | None:
    return next((g for g in goals if g.id == goal_id), None)
