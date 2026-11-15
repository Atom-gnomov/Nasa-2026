"""Розгінні ділянки (G16): маса впливає на прискорення й тривалість розгону, але не на швидкість на пасивній ділянці."""

import pytest

from app.core import burns


def test_rocket_equation_burn():
    b = burns.burn(10_000.0, 3130.0, 450.0, 50_000.0)
    assert b["mass_end_kg"] == pytest.approx(10_000.0 * 0.4915, rel=0.01)
    assert b["propellant_kg"] == pytest.approx(10_000.0 - b["mass_end_kg"])
    assert b["duration_s"] == pytest.approx(b["propellant_kg"] * 450.0 * burns.G0 / 50_000.0)
    assert b["accel_end_m_s2"] > b["accel_start_m_s2"]  # маса зменшується — прискорення зростає
    with pytest.raises(ValueError):
        burns.burn(0, 3130, 450, 1)


def test_heavier_payload_means_slower_acceleration_and_longer_burn():
    light = burns.tli_burn(5_000.0, 17_500.0, 3130.0, 450.0)
    heavy = burns.tli_burn(16_000.0, 17_500.0, 3130.0, 450.0)
    assert heavy["accel_start_g"] < light["accel_start_g"]
    assert heavy["duration_s"] > light["duration_s"]
    assert heavy["thrust_n"] == pytest.approx(light["thrust_n"]) or light["thrust_n"] < heavy["thrust_n"]


def test_full_rocket_matches_nominal_thrust_to_weight():
    full = burns.tli_burn(17_500.0, 17_500.0, 3130.0, 450.0)
    assert full["accel_start_g"] == pytest.approx(burns.DEFAULT_PARAMS.tli_tw)
    assert 400.0 < full["duration_s"] < 900.0  # хвилини, а не години чи секунди
    assert not full["overloaded"] and full["launches"] == 1


def test_overload_and_nearly_full_rocket_warn():
    over = burns.tli_burn(30_000.0, 17_500.0, 3130.0, 450.0)
    assert over["overloaded"] and over["launches"] == 2 and over["mass_start_kg"] == pytest.approx(15_000.0)
    assert "більший за місткість" in over["warnings"][0]
    near = burns.tli_burn(16_500.0, 17_500.0, 3130.0, 450.0)
    assert near["warnings"] and "90 %" in near["warnings"][0]
    assert not burns.tli_burn(8_000.0, 17_500.0, 3130.0, 450.0)["warnings"]


def test_acceleration_is_capped_and_lower_for_crewed():
    tiny = burns.tli_burn(500.0, 17_500.0, 3130.0, 450.0)  # дуже легкий вантаж на великій ракеті
    assert tiny["accel_start_g"] <= burns.DEFAULT_PARAMS.max_g_robotic + 1e-9
    crewed = burns.tli_burn(500.0, 17_500.0, 3130.0, 450.0, crewed=True)
    assert crewed["accel_start_g"] <= burns.DEFAULT_PARAMS.max_g_crewed + 1e-9 < tiny["accel_start_g"] + 1
    assert crewed["max_g"] < tiny["max_g"]
