import pytest

from app.core import payload
from app.core.payload import LEVELS, PayloadParams, payload_budget, size_from_level


def test_levels_and_sizes():
    assert [size_from_level(k) for k in ("min", "basic", "extended", "max")] == pytest.approx([0, 1 / 3, 2 / 3, 1])
    assert size_from_level(0.25) == 0.25
    for bad in ("huge", -0.1, 1.1, True, None):
        with pytest.raises(ValueError):
            size_from_level(bad)
    assert set(LEVELS) == {"min", "basic", "extended", "max"}


def test_uncrewed_example_by_hand():
    # обладнання «basic»: 30 + 1470/3 = 520 кг, 20 + 780/3 = 280 Вт; панелі 280/60; без акумуляторів
    b = payload_budget({"equipment": "basic"})
    assert b.masses_kg["equipment"] == pytest.approx(520.0)
    assert b.masses_kg["life_support"] == 0.0 and b.masses_kg["comfort"] == 0.0
    assert b.power_w == pytest.approx(280.0) and b.heat_w == b.power_w
    assert b.panel_kg == pytest.approx(280 / 60) and b.battery_kg == 0.0
    subtotal = 520 + 280 / 60
    assert b.masses_kg["structure"] == pytest.approx(0.25 * subtotal)
    assert b.total_kg == pytest.approx(subtotal * 1.25 * 1.20) == pytest.approx(787.0, abs=0.01)


def test_crewed_example_by_hand():
    # 4 людини, 30 діб, життєзабезпечення й зручності «basic» (s = 1/3)
    b = payload_budget({"equipment": "min", "life_support": "basic", "comfort": "basic"}, crew=4, days=30)
    # витратні 5 − 3·s = 4,0 кг/люд·добу → 480; обладнання 150 + 450/3 = 300 на людину → 1200; захист 400/3
    assert b.masses_kg["life_support"] == pytest.approx(480 + 1200 + 400 / 3)
    # об'єм 2 + 10/3 м³ на людину ·40 кг/м³ → 853,3; побут 0,5 + 1,5/3 = 1,0 кг/люд·добу → 120
    assert b.masses_kg["comfort"] == pytest.approx(4 * (2 + 10 / 3) * 40 + 120)
    # потужність: обладнання 20 + 4·(300 + 700/3 + 50 + 250/3)
    assert b.power_w == pytest.approx(20 + 4 * (300 + 700 / 3 + 50 + 250 / 3))


def test_uncrewed_ignores_life_support_and_comfort_sizes():
    a = payload_budget({"life_support": "max", "comfort": "max"}, crew=0, days=100)
    b = payload_budget({"life_support": "min", "comfort": "min"}, crew=0, days=100)
    assert a.total_kg == b.total_kg and a.masses_kg["life_support"] == 0.0


@pytest.mark.parametrize("category", payload.CATEGORIES)
def test_bigger_size_never_lighter_for_crewed(category):
    totals = [payload_budget({c: ("basic" if c != category else lvl) for c in payload.CATEGORIES},
                             crew=4, days=30).total_kg for lvl in ("min", "basic", "extended", "max")]
    # життєзабезпечення: вищий рівень регенерації зменшує витратні, але додає обладнання й захист — у сумі зростає
    assert totals == sorted(totals) and totals[0] < totals[-1]


def test_consumables_scale_with_crew_times_days():
    one = payload_budget({"life_support": "min"}, crew=1, days=10).masses_kg["life_support"]
    many = payload_budget({"life_support": "min"}, crew=3, days=40).masses_kg["life_support"]
    fixed = 150.0  # на людину при s = 0, захисту немає
    assert one == pytest.approx(10 * 5.0 + fixed)
    assert many == pytest.approx(3 * 40 * 5.0 + 3 * fixed)


def test_batteries_follow_longest_night():
    day = payload_budget({"equipment": "max"}, longest_night_h=0)
    night = payload_budget({"equipment": "max"}, longest_night_h=100)
    assert day.battery_kg == 0.0
    assert night.battery_kg == pytest.approx(800 * 100 / (150 * 0.8))  # 800 Вт · 100 год / (150 Вт·год/кг · 0,8)
    assert night.total_kg > day.total_kg


def test_total_is_sum_of_parts_and_range_brackets_it():
    b = payload_budget({"equipment": "extended", "life_support": "extended", "comfort": "extended"},
                       crew=2, days=14, longest_night_h=50)
    assert sum(b.masses_kg.values()) == pytest.approx(b.total_kg)
    assert b.payload_kg == pytest.approx(sum(b.masses_kg[c] for c in payload.CATEGORIES))
    lo, hi = b.total_range_kg
    assert lo < b.total_kg < hi


def test_custom_params_and_to_dict():
    tiny = PayloadParams(structure_fraction=0.0, margin_fraction=0.0, uncertainty=(1.0, 1.0))
    b = payload_budget({"equipment": "min"}, params=tiny)
    assert b.total_kg == pytest.approx(30 + 20 / 60) and b.total_range_kg == (b.total_kg, b.total_kg)
    d = b.to_dict()
    assert d["masses_kg"]["equipment"] == 30.0 and d["crew"] == 0


@pytest.mark.parametrize("kwargs", [
    {"sizes": {"weapons": "max"}}, {"sizes": {"equipment": 2}}, {"crew": -1}, {"crew": 7}, {"crew": 1.5},
    {"crew": True}, {"days": -1}, {"days": 400}, {"longest_night_h": -5},
])
def test_validation(kwargs):
    with pytest.raises(ValueError):
        payload_budget(**kwargs)
