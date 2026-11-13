from app.core.advice_check import collect_fact_numbers, numbers_in, unknown_numbers

FACTS = {
    "site": {"name": "Apollo 11", "lat": 0.67416},
    "period": {"start": "2027-07-01T00:00:00Z"},
    "metrics": {"sun_fraction": 0.4712, "comm_hours": 343.4, "score_pct": 71.48},
    "comparison": {"score_delta_pct": 22.53},
}


def test_numbers_in_text_with_comma_and_minus():
    assert numbers_in("кут −5,5° і 12.5 год, 40%") == [-5.5, 12.5, 40.0]


def test_collects_numbers_from_values_and_strings_but_not_booleans():
    nums = collect_fact_numbers({"a": 1.5, "b": True, "c": "Apollo 11, 2027-07-01", "d": [2, {"e": 3.25}]})
    assert {1.5, 11.0, 2027.0, 7.0, 1.0, 2.0, 3.25} <= nums
    assert collect_fact_numbers({"b": True, "c": False}) == set()


def test_known_numbers_pass_including_rounding_percent_and_days():
    text = "Бал 71.5 пункта, різниця 22.5, Сонце близько 47 %, зв'язок 343 год, тобто 14.3 доби. Apollo 11, 2027."
    assert unknown_numbers(text, FACTS) == []


def test_invented_numbers_are_reported():
    bad = unknown_numbers("Потрібно 8765 Вт і кут 33.3°, бал 71.5", FACTS)
    assert "8765" in bad and "33.3" in bad and "71.5" not in bad


def test_small_integers_are_not_flagged():
    assert unknown_numbers("Зробіть 3 кроки: 1. змініть дату, 2. область", {"x": 100}) == []


def test_tolerance_is_tight_enough():
    assert unknown_numbers("бал 75", FACTS) == ["75"]
