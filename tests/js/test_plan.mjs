// Тести вкладки «План місії» (app/static/js/plan.js) у Node без браузера.
import { test } from "node:test";
import assert from "node:assert/strict";

const plan = await import(new URL("../../app/static/js/plan.js", import.meta.url).href);

const state = { datetime: "2027-03-01T06:00Z" };

test("запит: вимоги беруться з «Підбору» (регіон, період, пороги, пріоритети), профіль і ракета — з форми", () => {
  const search = { days: 5, regionKey: "pole", minSunHours: 48, maxSlopeDeg: 10, minEarthPct: 25,
                   priorities: [{ id: "comms", on: true }, { id: "energy", on: true }, { id: "radiation", on: false }] };
  const body = plan.buildPlanRequest({ ...plan.DEFAULT_FORM }, state, search);
  assert.equal(body.start, "2027-03-01T06:00:00Z");
  assert.equal(body.end, "2027-03-06T06:00:00Z");
  assert.deepEqual(body.region, { lat_min: -90, lat_max: -80 });
  assert.deepEqual(body.priorities, ["comms", "energy"]);
  assert.equal(body.min_sun_hours, 48);
  assert.equal(body.max_slope_deg, 10);
  assert.equal(body.min_earth_fraction, 0.25);
  assert.ok(!("min_comm_hours" in body) && !("vehicle" in body) && !("launch_site_id" in body));
  assert.deepEqual(body.trajectories, ["direct"]); // календар — дата посадки: маршрут завжди явний, типово швидкий
  assert.equal(body.mission_profile, "uncrewed");
  assert.equal(body.days, 0);
});

test("запит: пілотована — екіпаж і доби, вибрана ракета й траєкторія", () => {
  const body = plan.buildPlanRequest({ ...plan.DEFAULT_FORM, profile: "crewed", crew: "3", days: "14",
                                       vehicle: "sls", trajectory: "direct" }, state);
  assert.equal(body.crew, 3);
  assert.equal(body.days, 14);
  assert.equal(body.vehicle, "sls");
  assert.deepEqual(body.trajectories, ["direct"]);
});

test("запит: без збережених вимог «Підбору» — типові (півд. полюс, 30 діб); без дати — помилка", () => {
  const body = plan.buildPlanRequest(plan.DEFAULT_FORM, state);
  assert.equal((Date.parse(body.end) - Date.parse(body.start)) / 86400000, 30);
  assert.deepEqual(body.region, { lat_min: -90, lat_max: -80 });
  assert.deepEqual(body.priorities, ["energy", "comms"]);
  assert.throws(() => plan.buildPlanRequest(plan.DEFAULT_FORM, { datetime: "?" }));
});

test("запит: обраний майданчик старту передається, «оптимально» й порожній — ні", () => {
  assert.equal(plan.buildPlanRequest({ ...plan.DEFAULT_FORM, launchSite: "kourou" }, state).launch_site_id, "kourou");
  assert.ok(!("launch_site_id" in plan.buildPlanRequest({ ...plan.DEFAULT_FORM, launchSite: "auto:fuel:any" }, state)));
  assert.ok(!("launch_site_id" in plan.buildPlanRequest({ ...plan.DEFAULT_FORM, launchSite: "" }, state)));
});

const response = {
  auto_selected: 1,
  plans: [{
    rank: 1, score_pct: 71.234, mass_moon_kg: 1234.5,
    landing: { moon_site: { site_id: null, name: null, lat: -89.5, lon: 12.25 } },
    requirements: { feasible: true, violations: [], warnings: [{ requirement: "min_earth_fraction", value: 0.1, required: 0.25, kind: "screening" }], unchecked: ["max_slope_deg"] },
    route: { departure_utc: "2027-03-02T00:00:00Z" },
    launch: { site: { name: "Kourou" }, vehicle: { name: "Falcon Heavy" }, trajectory: "direct", duration_days: [3.5, 4.2],
              launch_cost_usd: [2.0e7, 3.5e7], risk: { p: 0.031, band_label: "низький" } },
  }, {
    rank: 2, score_pct: 40, mass_moon_kg: 900,
    landing: { moon_site: { site_id: "shackleton", name: "Shackleton", lat: -89.9, lon: 0 } },
    requirements: { feasible: false, violations: [{ requirement: "max_slope_deg", value: 12, required: 10 }], warnings: [], unchecked: [] },
    launch: null,
  }],
};

test("рядки: лідер виділений, координати без назви, відсутній запуск не дає undefined", () => {
  const rows = plan.planRows(response);
  assert.equal(rows.length, 2);
  assert.ok(rows[0].lead && !rows[1].lead);
  assert.ok(rows[0].feasible && !rows[1].feasible);
  assert.equal(rows[0].cells[1], "-89.50°, 12.25°");
  assert.equal(rows[0].cells[5], "2027-03-02");
  assert.equal(rows[1].cells[1], "Shackleton");
  for (const row of rows) for (const c of row.cells) assert.ok(typeof c === "string" && !/undefined|NaN/.test(c), c);
});

test("порівняння носіїв: заповненість у таблиці й вибір варіанта для спільного вибору польоту", () => {
  assert.equal(plan.fillText(null), "—");
  assert.equal(plan.fillText({ utilization: 0.823, launches: 1 }), "82 %");
  assert.match(plan.fillText({ utilization: 1.29, launches: 2 }), /129 % · 2 пуски/);
  const rows = plan.planRows({ ...response, plans: [{ ...response.plans[0], launch: { ...response.plans[0].launch, utilization: 0.5, launches: 1 } }] });
  assert.equal(rows[0].cells[7], "50 %");
  const choice = plan.launchChoiceFromPlan({ ...response.plans[0], launch: { ...response.plans[0].launch, site: { id: "kourou", name: "Kourou" }, vehicle: { id: "fh", name: "FH" } } });
  assert.deepEqual(choice, { site: "kourou", vehicle: "fh", trajectory: "direct", departure: "2027-03-02" });
  assert.equal(plan.launchChoiceFromPlan(response.plans[1]), null);
});

test("статус вимог: виконано / порушено / м'які / не перевірено", () => {
  assert.match(plan.requirementsText(response.plans[0].requirements), /^виконано · м'які: Земля видна · не перевірено: Нахил/);
  assert.match(plan.requirementsText(response.plans[1].requirements), /порушено: Нахил, ° 12 замість 10/);
});

test("запит: опції ракет передаються лише коли відрізняються від типових", () => {
  const base = plan.buildPlanRequest(plan.DEFAULT_FORM, state);
  assert.ok(!("include_design_targets" in base) && !("allow_multiple_launches" in base));
  const body = plan.buildPlanRequest({ ...plan.DEFAULT_FORM, includeDesign: false, multiLaunch: true }, state);
  assert.equal(body.include_design_targets, false);
  assert.equal(body.allow_multiple_launches, true);
});

test("запит: екіпаж із біометрією з вкладки «Місія» — crew_members замість crew, лише для пілотованої", () => {
  const members = [{ sex: "male", age: 35, mass_kg: 82, height_m: 1.78, activity: "active" }];
  const crewed = plan.buildPlanRequest({ ...plan.DEFAULT_FORM, profile: "crewed", crew: "3", days: "10", members,
                                         supplyDays: 12, reservePct: 20 }, state);
  assert.deepEqual(crewed.crew_members, members);
  assert.ok(!("crew" in crewed));
  assert.equal(crewed.supply_days, 12);
  assert.equal(crewed.reserve_fraction, 0.2);
  const uncrewed = plan.buildPlanRequest({ ...plan.DEFAULT_FORM, members }, state);
  assert.ok(!("crew_members" in uncrewed));
});

test("запит: пілотована — завжди пряма траєкторія, навіть якщо обрано іншу", () => {
  const body = plan.buildPlanRequest({ ...plan.DEFAULT_FORM, profile: "crewed", trajectory: "low_energy" }, state);
  assert.deepEqual(body.trajectories, ["direct"]);
  const robot = plan.buildPlanRequest({ ...plan.DEFAULT_FORM, trajectory: "low_energy" }, state);
  assert.deepEqual(robot.trajectories, ["low_energy"]);
  assert.deepEqual(plan.buildPlanRequest({ ...plan.DEFAULT_FORM, trajectory: "any" }, state).trajectories, ["direct"]);
});

test("запит: вибрана на кроці 5 точка посадки передається, пошук по області не робиться; прапорець повертає пошук", () => {
  const withPoint = plan.buildPlanRequest({ ...plan.DEFAULT_FORM }, { datetime: "2027-03-01T06:00Z", lat: -82, lon: 28.8, site: "shackleton" });
  assert.deepEqual(withPoint.landing_point, { lat: -82, lon: 28.8, site_id: "shackleton" });
  const research = plan.buildPlanRequest({ ...plan.DEFAULT_FORM, useChosenPoint: false }, { datetime: "2027-03-01T06:00Z", lat: -82, lon: 28.8 });
  assert.ok(!("landing_point" in research));
  assert.ok(!("landing_point" in plan.buildPlanRequest({ ...plan.DEFAULT_FORM }, state)));
  assert.ok(!("departure" in withPoint)); // дата старту завжди обчислюється від дати посадки
});

test("дата й час старту в таблиці: момент UTC, якщо є вікно запуску; без нього — лише дата", () => {
  assert.equal(plan.launchMoment({ route: { departure_utc: "2026-12-05T14:22:10Z" }, launch_windows_utc: ["2026-12-05T14:22:10Z"] }), "2026-12-05 14:22 UTC");
  assert.equal(plan.launchMoment({ route: { departure_utc: "2026-12-05T00:00:00Z" }, launch_windows_utc: [] }), "2026-12-05");
  assert.equal(plan.launchMoment({ route: null }), "—");
});
