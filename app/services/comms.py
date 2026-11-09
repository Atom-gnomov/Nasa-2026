"""Зв'язок: затримка сигналу Земля ↔ Місяць."""

SPEED_OF_LIGHT_KM_S = 299_792.458


def signal_delay_s(distance_km: float) -> float:
    """Затримка сигналу в один бік, секунди."""
    if distance_km < 0:
        raise ValueError("Відстань не може бути від'ємною")
    return distance_km / SPEED_OF_LIGHT_KM_S
