// Тести вкладки «План місії» (app/static/js/plan.js) у Node без браузера.
import { test } from "node:test";
import assert from "node:assert/strict";

const plan = await import(new URL("../../app/static/js/plan.js", import.meta.url).href);

const state = { datetime: "2027-03-01T06:00Z" };

test("запит: період від календаря, вимоги лише задані, профіль і ракета", () => {
  const body = plan.buildPlanRequest({ ...plan.DEFAULT_FORM, maxSlope: "10", minEarth: "0.25", periodDays: 5 }, state);
  assert.equal(body.start, "2027-03-01T06:00:00Z");
  assert.equal(body.end, "2027-03-06T06:00:00Z");
  assert.equal(body.max_slope_deg, 10);
  assert.equal(body.min_earth_fraction, 0.25);
  assert.ok(!("min_sun_hours" in body) && !("vehicle" in body) && !("trajectories" in body));
  assert.equal(body.mission_profile, "uncrewed");
  assert.equal(body.departure_days, 7);
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

test("запит: період обмежено 1…60 діб; без дати — помилка", () => {
  const body = plan.buildPlanRequest({ ...plan.DEFAULT_FORM, periodDays: 500 }, state);
  assert.equal((Date.parse(body.end) - Date.parse(body.start)) / 86400000, 60);
  assert.throws(() => plan.buildPlanRequest(plan.DEFAULT_FORM, { datetime: "?" }));
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
