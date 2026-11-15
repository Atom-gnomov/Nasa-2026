"""POST /api/mission: контракт, безпілотна й пілотована місії, широта старту, помилки (задача B9)."""

import pytest

from app.core import cost, payload, risk
from tests.test_contracts import api_validator, assert_valid


def post(client, body):
    return client.post("/api/mission", json=body)


def test_empty_request_is_an_uncrewed_mission_and_matches_contract(client):
    res = post(client, {})
    assert res.status_code == 200
    data = res.get_json()
    assert_valid(api_validator("MissionResponse"), data)
    assert data["provisional"] is True
    assert data["launch_lat"] == 0.0 and data["launch_site_id"] is None
    assert data["payload"]["crew"] == 0
    assert data["payload"]["masses_kg"]["life_support"] == 0 and data["payload"]["masses_kg"]["comfort"] == 0
    assert data["risk"]["p_crew_loss"] is None and data["risk"]["crew_band"] is None


def test_response_equals_the_core_models(client):
    body = {"crew": 3, "days": 20, "sizes": {"equipment": "extended", "life_support": 0.7, "comfort": "min"},
            "trajectory": "low_energy", "launch_lat": 28.5, "longest_night_h": 250}
    data = post(client, body).get_json()
    budget = payload.payload_budget(body["sizes"], crew=3, days=20, longest_night_h=250)
    estimate = cost.mission_cost(budget.masses_kg, trajectory="low_energy", latitude_deg=28.5)
    assessment = risk.assess(estimate.utilization, estimate.mass_moon_kg, budget.sizes, crew=3,
                             trajectory="low_energy")
    assert data["payload"]["total_kg"] == pytest.approx(budget.total_kg)
    assert data["cost"]["total_usd"] == pytest.approx(list(estimate.total_usd))
    assert data["risk"]["p_total"] == pytest.approx(assessment.p_total)
    assert data["risk"]["p_crew_loss"] == pytest.approx(assessment.p_crew_loss)
    assert data["risk"]["band_label"] == assessment.band_label


def test_launch_site_id_sets_latitude_from_catalog(client):
    kourou = post(client, {"launch_site_id": "kourou"}).get_json()
    equator = post(client, {}).get_json()
    assert kourou["launch_site_id"] == "kourou" and 5 < kourou["launch_lat"] < 6
    high = post(client, {"launch_lat": 60}).get_json()
    assert equator["cost"]["site_factor"] <= kourou["cost"]["site_factor"] < high["cost"]["site_factor"]


def test_crewed_mission_is_heavier_and_has_crew_risk(client):
    uncrewed = post(client, {"days": 14}).get_json()
    crewed = post(client, {"crew": 4, "days": 14}).get_json()
    assert crewed["payload"]["total_kg"] > uncrewed["payload"]["total_kg"]
    assert crewed["cost"]["total_usd"][0] > uncrewed["cost"]["total_usd"][0]
    assert crewed["risk"]["p_crew_loss"] is not None and crewed["risk"]["crew_band_label"]


def test_low_energy_needs_less_mass_in_leo_and_takes_longer(client):
    direct = post(client, {"crew": 2, "days": 10}).get_json()["cost"]
    slow = post(client, {"crew": 2, "days": 10, "trajectory": "low_energy"}).get_json()["cost"]
    assert slow["mass_leo_kg"] < direct["mass_leo_kg"]
    assert slow["flight_time_days"][0] > direct["flight_time_days"][1]


@pytest.mark.parametrize("body, status", [
    ({"crew": 7}, 400), ({"crew": -1}, 400), ({"crew": 1.5}, 400), ({"crew": True}, 400),
    ({"days": -1}, 400), ({"days": 1000}, 400), ({"days": "10"}, 400),
    ({"longest_night_h": -5}, 400),
    ({"sizes": {"equipment": "huge"}}, 400), ({"sizes": {"comfort": 1.5}}, 400),
    ({"sizes": {"weapons": "max"}}, 400), ({"sizes": "max"}, 400),
    ({"trajectory": "teleport"}, 400),
    ({"launch_lat": 91}, 400), ({"launch_lat": "x"}, 400),
    ({"launch_site_id": "kourou", "launch_lat": 5}, 400), ({"launch_site_id": 5}, 400),
    ({"launch_site_id": "no-such-site"}, 404),
    ({"surprise": 1}, 400),
])
def test_invalid_requests(client, body, status):
    res = post(client, body)
    assert res.status_code == status, res.get_json()
    assert_valid(api_validator("Error"), res.get_json())


def test_non_object_body_is_rejected(client):
    res = client.post("/api/mission", json=[1, 2, 3])
    assert res.status_code == 400
    assert_valid(api_validator("Error"), res.get_json())


def test_no_body_is_treated_as_defaults(client):
    assert client.post("/api/mission").status_code == 200


# ---------- B16: система запуску ----------
def test_launch_systems_list_matches_contract(client):
    res = client.get("/api/launch-systems")
    assert res.status_code == 200
    data = res.get_json()
    assert isinstance(data, list) and len(data) >= 3
    for item in data:
        assert_valid(api_validator("LaunchSystem"), item)
    kinds = {item["kind"] for item in data}
    assert kinds == {"spaceport", "sea_platform", "air_launch"}
    zenit = next(i for i in data if i["id"] == "zenit-3sl-sea-launch")
    assert zenit["capacity_leo_kg"] is None  # у джерелах лише ГПО


def test_mission_with_launch_system_uses_catalog_capacity_and_reports_provisional_fields(client):
    data = post(client, {"crew": 2, "days": 10, "launch_system_id": "ariane-64"}).get_json()
    assert_valid(api_validator("MissionResponse"), data)
    ls = data["launch_system"]
    assert ls["rocket"]["capacity_leo_kg"] == 21600.0
    # D8: база відмови — зі статистики польотів у каталозі; ціни Ariane 64 в каталозі немає
    assert ls["provisional_fields"] == ["price_usd_per_kg"]
    assert ls["fit"]["utilization"] == pytest.approx(data["cost"]["mass_leo_kg"] / 21600.0)
    assert data["launch_site_id"] == "kourou" and 5 < data["launch_lat"] < 6  # широта з місця системи


def test_smaller_system_gives_higher_utilization_than_default_rocket(client):
    base = post(client, {"crew": 2, "days": 10}).get_json()
    small = post(client, {"crew": 2, "days": 10, "launch_system_id": "ariane-62"}).get_json()
    assert small["cost"]["utilization"] > base["cost"]["utilization"]
    assert small["launch_system"]["fit"]["launches"] >= 2


def test_without_launch_system_nothing_changes(client):
    assert post(client, {}).get_json()["launch_system"] is None


def test_air_launch_system_cannot_carry_a_lunar_lander(client):
    data = post(client, {"launch_system_id": "pegasus-xl"}).get_json()
    fit = data["launch_system"]["fit"]
    assert not fit["fits_single_launch"] and "літака-носія" in fit["note"]
    assert data["launch_site_id"] is None and data["launch_lat"] == 0.0  # повітряний старт місця не має


def test_explicit_site_overrides_system_site(client):
    data = post(client, {"launch_system_id": "ariane-64", "launch_lat": 45}).get_json()
    assert data["launch_lat"] == 45 and data["launch_site_id"] is None


@pytest.mark.parametrize("body, status", [
    ({"launch_system_id": "no-such"}, 404),
    ({"launch_system_id": 7}, 400),
    ({"launch_system_id": "zenit-3sl-sea-launch"}, 400),  # немає місткості на НОО
])
def test_invalid_launch_system(client, body, status):
    res = post(client, body)
    assert res.status_code == status, res.get_json()
    assert_valid(api_validator("Error"), res.get_json())


# ---------- B17: профіль місії ----------
def test_without_profile_response_has_no_profile(client):
    assert post(client, {}).get_json()["profile"] is None


def test_uncrewed_profile_forces_zero_crew_and_matches_contract(client):
    data = post(client, {"mission_profile": "uncrewed"}).get_json()
    assert_valid(api_validator("MissionResponse"), data)
    assert data["profile"]["profile"] == "uncrewed" and data["payload"]["crew"] == 0
    assert data["risk"]["p_crew_loss"] is None


def test_crewed_profile_defaults_crew_and_marks_it_as_profile_choice(client):
    data = post(client, {"mission_profile": "crewed", "days": 10}).get_json()
    assert_valid(api_validator("MissionResponse"), data)
    assert data["payload"]["crew"] == data["profile"]["crew"] >= 1
    assert "crew" in data["profile"]["from_profile"]
    assert data["risk"]["p_crew_loss"] is not None


def test_explicit_crew_wins_over_profile_default(client):
    data = post(client, {"mission_profile": "crewed", "crew": 4, "days": 10}).get_json()
    assert data["payload"]["crew"] == 4 and "crew" not in data["profile"]["from_profile"]
    same = post(client, {"crew": 4, "days": 10}).get_json()
    assert data["cost"]["total_usd"] == same["cost"]["total_usd"]  # профіль не змінює розрахунок, лише перевіряє вхід


@pytest.mark.parametrize("body", [
    {"mission_profile": "robot"},
    {"mission_profile": "uncrewed", "crew": 2},
    {"mission_profile": "crewed", "crew": 0},
    {"mission_profile": "crewed", "crew": 7},
    {"mission_profile": "crewed", "crew": True},
])
def test_invalid_profile_requests(client, body):
    res = post(client, body)
    assert res.status_code == 400, res.get_json()
    assert_valid(api_validator("Error"), res.get_json())


# ---------- B19: єдиний каталог засобів запуску (D6 + D7) ----------
def test_launch_systems_list_contains_both_catalogs(client):
    data = client.get("/api/launch-systems").get_json()
    for item in data:
        assert_valid(api_validator("LaunchSystem"), item)
    ids = [i["id"] for i in data]
    assert len(ids) == len(set(ids))  # ідентифікатори унікальні в єдиному каталозі
    assert {"launch_systems", "rockets"} == {i["catalog"] for i in data}
    assert {"falcon-9", "starship", "sls-block-1", "ariane-64", "pegasus-xl"} <= set(ids)
    sls = next(i for i in data if i["id"] == "sls-block-1")
    assert sls["capacity_leo_kg"] is None and sls["capacity_tli_kg"] == 27000 and sls["capacity_basis"] == "tli"
    starship = next(i for i in data if i["id"] == "starship")
    assert starship["status"] == "in_testing" and starship["verified_by_flight"] is False


def test_mission_accepts_a_rocket_from_d7_catalog(client):
    data = post(client, {"crew": 2, "days": 10, "launch_system_id": "falcon-heavy"}).get_json()
    assert_valid(api_validator("MissionResponse"), data)
    ls = data["launch_system"]
    assert ls["system"]["catalog"] == "rockets" and ls["rocket"]["capacity_basis"] == "leo"
    assert ls["rocket"]["capacity_leo_kg"] == 63800.0
    assert data["launch_site_id"] == "cape-canaveral"  # місце старту — з каталогу ракети


def test_tli_only_rocket_is_converted_to_equivalent_leo_capacity(client):
    """SLS має лише місткість на TLI (27 т): її переведено на НОО множником розгінного блока; заповненість узгоджена."""
    data = post(client, {"crew": 2, "days": 10, "launch_system_id": "sls-block-1"}).get_json()
    ls = data["launch_system"]
    assert ls["rocket"]["capacity_basis"] == "tli"
    assert ls["rocket"]["capacity_leo_kg"] > 27000  # еквівалент на НОО більший за масу після TLI
    assert ls["fit"]["utilization"] == pytest.approx(data["cost"]["utilization"])
    assert ls["fit"]["utilization"] == pytest.approx(data["cost"]["mass_leo_kg"] / ls["rocket"]["capacity_leo_kg"])


def test_tli_equivalent_capacity_does_not_depend_on_the_trajectory_choice(client):
    """Множник розгінного блока (Δv TLI) однаковий для прямої й економної траєкторії; відрізняється лише посадка."""
    direct = post(client, {"launch_system_id": "sls-block-1", "trajectory": "direct"}).get_json()
    slow = post(client, {"launch_system_id": "sls-block-1", "trajectory": "low_energy"}).get_json()
    assert slow["launch_system"]["rocket"]["capacity_leo_kg"] == pytest.approx(
        direct["launch_system"]["rocket"]["capacity_leo_kg"])
    assert slow["cost"]["mass_leo_kg"] < direct["cost"]["mass_leo_kg"]  # економна легша на НОО


def test_design_target_rocket_is_marked_in_the_listing_and_still_calculable(client):
    listing = {i["id"]: i for i in client.get("/api/launch-systems").get_json()}
    lm10 = listing["long-march-10"]
    assert lm10["status"] == "design_target" and lm10["verified_by_flight"] is False
    data = post(client, {"launch_system_id": "long-march-10"}).get_json()
    assert data["launch_system"]["system"]["verified_by_flight"] is False  # проєктну ціль не видаємо за підтверджену


# ---------- M22: таблиці D4 у моделі маси ----------
def test_sourced_basis_uses_nasa_ranges_and_reports_them(client):
    base = {"crew": 2, "days": 10, "longest_night_h": 100}
    model = client.post("/api/mission", json=base).get_json()
    sourced = client.post("/api/mission", json={**base, "parameters_basis": "sourced"}).get_json()
    assert model["parameters_basis"] == "model" and model["sourced_parameters"] == []
    assert sourced["parameters_basis"] == "sourced"
    ids = {p["id"] for p in sourced["sourced_parameters"]}
    assert {"equipment_mass_kg", "consumables_kg_per_person_day", "battery_depth_of_discharge"} <= ids
    assert "habitable_volume_m3_per_person" not in ids and "lunar_delivery_usd_per_kg" not in ids
    assert sourced["payload"]["total_kg"] != model["payload"]["total_kg"]
    assert_valid(api_validator("MissionResponse"), sourced)


def test_sourced_equipment_mass_matches_source_range(client):
    low = client.post("/api/mission", json={"sizes": {"equipment": 0}, "parameters_basis": "sourced"}).get_json()
    high = client.post("/api/mission", json={"sizes": {"equipment": 1}, "parameters_basis": "sourced"}).get_json()
    assert low["payload"]["masses_kg"]["equipment"] == pytest.approx(10.0)
    assert high["payload"]["masses_kg"]["equipment"] == pytest.approx(475.0)


def test_unknown_parameters_basis_is_rejected(client):
    res = client.post("/api/mission", json={"parameters_basis": "magic"})
    assert res.status_code == 400


# ---------- M24 / B21: екіпаж із біометрією, запаси, журнал ----------
CREW = [{"sex": "male", "mass_kg": 90, "height_m": 1.85, "age": 40, "activity": "active"},
        {"sex": "female", "mass_kg": 58, "height_m": 1.62, "age": 33}]


def test_crew_members_drive_supplies_and_payload(client):
    base = {"mission_profile": "crewed", "days": 20}
    res = client.post("/api/mission", json={**base, "crew_members": CREW})
    assert res.status_code == 200, res.get_json()
    data = res.get_json()
    assert_valid(api_validator("MissionResponse"), data)
    assert data["payload"]["crew"] == 2
    cs = data["crew_supplies"]
    assert len(cs["members"]) == 2 and cs["supply_days"] == pytest.approx(23.0)
    assert cs["loaded_total_kg"] > 0 and len(cs["log"]) == 21 and not cs["warnings"]
    # витратні в масі життєзабезпечення = завезені запаси + обладнання й захист
    assert data["payload"]["masses_kg"]["life_support"] > cs["loaded_total_kg"]
    heavier = [{**CREW[0], "mass_kg": 120}, CREW[1]]
    more = client.post("/api/mission", json={**base, "crew_members": heavier}).get_json()
    assert more["crew_supplies"]["loaded_total_kg"] > cs["loaded_total_kg"]


def test_supply_shortage_is_reported_in_the_response(client):
    data = client.post("/api/mission", json={"mission_profile": "crewed", "days": 20, "crew_members": CREW,
                                             "supply_days": 15}).get_json()
    assert [w["kind"] for w in data["crew_supplies"]["warnings"]] == ["shortage"]
    assert data["crew_supplies"]["log"][-1]["worst"] == "shortage"


def test_categories_expose_numbers_for_sliders(client):
    data = client.post("/api/mission", json={"mission_profile": "crewed", "crew": 2, "days": 10}).get_json()
    for name in ("equipment", "life_support", "comfort"):
        c = data["categories"][name]
        assert c["mass_kg"] == data["payload"]["masses_kg"][name] and c["usd"][0] < c["usd"][1]
    assert data["categories"]["life_support"]["power_w"] > 0
    assert data["crew_supplies"] is None


@pytest.mark.parametrize("extra", [{"crew": 3}, {"mission_profile": "uncrewed"}, {"reserve_fraction": 9},
                                   {"crew_members": []}, {"crew_members": [{"sex": "x"}]}])
def test_invalid_crew_members_are_rejected(client, extra):
    body = {"days": 10, "crew_members": CREW, **extra}
    res = client.post("/api/mission", json=body)
    assert res.status_code == 400, res.get_json()


# ---------- G16: розгінні ділянки залежать від маси ----------
def test_flight_phases_depend_on_payload_mass(client):
    light = client.post("/api/mission", json={"sizes": {"equipment": "min"}}).get_json()
    heavy = client.post("/api/mission", json={"sizes": {"equipment": "max"}}).get_json()
    assert_valid(api_validator("MissionResponse"), heavy)
    a, b = light["flight_phases"]["tli"], heavy["flight_phases"]["tli"]
    assert b["mass_start_kg"] > a["mass_start_kg"]
    assert b["accel_start_g"] < a["accel_start_g"] and b["duration_s"] > a["duration_s"]
    assert a["dv_m_s"] == b["dv_m_s"]  # швидкість на пасивній ділянці від маси не залежить


def test_flight_phases_warn_when_the_rocket_is_overloaded(client):
    sizes = {"equipment": "max", "life_support": "max", "comfort": "max"}
    data = client.post("/api/mission", json={"mission_profile": "crewed", "crew": 6, "days": 300,
                                             "sizes": sizes}).get_json()
    tli = data["flight_phases"]["tli"]
    assert tli["overloaded"] and tli["warnings"] and tli["launches"] >= 2
    assert tli["max_g"] == 3.0  # пілотована — менше перевантаження


def test_supply_kg_changes_balance_economics_and_feasibility(client):
    base = {"mission_profile": "crewed", "days": 20, "crew_members": CREW}
    auto = client.post("/api/mission", json=base).get_json()
    assert auto["mission_feasible"] is True and auto["crew_supplies"]["summary"]["mission_ok"]
    eco = auto["crew_supplies"]["economics"]
    assert eco["usd_per_kg"][0] > 0 and eco["usd_per_kg"][1] > eco["usd_per_kg"][0] and eco["provisional"]
    need = auto["crew_supplies"]["resources"]["oxygen"]["required_kg"]
    lean = client.post("/api/mission", json={**base, "supply_kg": {"oxygen": need * 0.6}}).get_json()
    assert_valid(api_validator("MissionResponse"), lean)
    assert lean["mission_feasible"] is False
    cs = lean["crew_supplies"]
    assert cs["summary"]["first_shortage_resource"] == "oxygen"
    assert cs["summary"]["first_shortage_day"] == pytest.approx(12.0)
    assert cs["economics"]["deficit_usd"][0] > 0
    assert cs["loaded_total_kg"] < auto["crew_supplies"]["loaded_total_kg"], "менше кисню — менша маса навантаження"
    water = auto["crew_supplies"]["loaded_kg"]["water"] + 100
    fat = client.post("/api/mission", json={**base, "supply_kg": {"water": water}}).get_json()
    assert fat["crew_supplies"]["economics"]["excess_usd"][0] > 0 and fat["mission_feasible"] is True
    assert fat["cost"]["total_usd"][0] > auto["cost"]["total_usd"][0], "зайва вода дорожчає місію"


def test_supply_kg_errors(client):
    base = {"mission_profile": "crewed", "days": 20, "crew_members": CREW}
    for bad in ({"air": 5}, {"oxygen": -3}, {"oxygen": "x"}, "many"):
        res = client.post("/api/mission", json={**base, "supply_kg": bad})
        assert res.status_code == 400, bad
    assert client.get("/api/mission").status_code in (404, 405)
