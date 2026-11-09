import numpy as np
import pytest

from app.core.events import find_crossings, next_crossing


def test_sine_crossings():
    # Період 1 доба: схід у 0, захід у 0,5 доби; функція в jd.
    fn = lambda jd: np.sin(2 * np.pi * np.asarray(jd))  # noqa: E731
    crossings = find_crossings(fn, 0.1, 2.9, step_hours=1.0, tolerance_minutes=0.1)
    assert [c.rising for c in crossings] == [False, True, False, True, False]
    assert [c.jd for c in crossings] == pytest.approx([0.5, 1.0, 1.5, 2.0, 2.5], abs=1e-4)


def test_next_crossing_none():
    assert next_crossing(lambda jd: np.ones_like(jd), 0, 10, 1.0, rising=False) is None
