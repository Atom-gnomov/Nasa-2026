import math

import pytest

from app.core.grid import candidate_grid


def test_pole_row_is_single_point():
    pts = candidate_grid(-90, -88, -180, 180, 1)
    assert pts.count((-90.0, 0.0)) == 1
    assert sum(1 for la, _ in pts if la == -90.0) == 1


def test_longitude_count_follows_cos_latitude():
    pts = candidate_grid(0, 60, -180, 180, 10)
    row = lambda lat: sum(1 for la, _ in pts if abs(la - lat) < 1e-9)  # noqa: E731
    assert row(0) == 36
    assert row(60) == pytest.approx(36 * math.cos(math.radians(60)), abs=1)
    assert row(60) < row(30) < row(0)


def test_bounds_include_last_row_and_stay_inside():
    pts = candidate_grid(-90, -85, -30, 30, 2)
    lats = sorted({la for la, _ in pts})
    assert lats[0] == -90 and lats[-1] == -85  # крок 2 не ділить діапазон — останній рядок додано
    assert all(-30 <= lo <= 30 for _, lo in pts)


def test_points_are_unique_and_deterministic():
    a = candidate_grid(-90, -80, -180, 180, 2)
    assert a == candidate_grid(-90, -80, -180, 180, 2)
    assert len(a) == len(set(a))


def test_cap_raises_with_advice():
    with pytest.raises(ValueError, match="grid_step_deg"):
        candidate_grid(-90, 90, -180, 180, 0.5, max_candidates=100)


@pytest.mark.parametrize("args", [(10, -10, -180, 180, 2), (-100, 0, -180, 180, 2), (0, 10, 50, 40, 2),
                                  (0, 10, -190, 0, 2), (0, 10, -180, 180, 0)])
def test_invalid_region(args):
    with pytest.raises(ValueError):
        candidate_grid(*args)


def test_single_row_region():
    pts = candidate_grid(-85, -85, -180, 180, 5)
    assert {la for la, _ in pts} == {-85}
