"""Оцінка радіації від галактичних космічних променів (docs/MATH.md, §12). Друга черга."""

from __future__ import annotations

from app.core.horizon import HorizonMask

# Еквівалентна доза на відкритій поверхні, Chang'e 4 LND (Zhang et al., 2020).
OPEN_SURFACE_DOSE_USV_PER_DAY = 1369.0


def dose_rate_usv_per_day(mask: HorizonMask,
                          open_surface_dose: float = OPEN_SURFACE_DOSE_USV_PER_DAY) -> float:
    """Доза ∝ частка відкритого неба (ізотропні ГКП, без вторинного випромінювання ґрунту)."""
    return open_surface_dose * mask.sky_view_fraction()
