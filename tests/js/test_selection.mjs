// Тести наскрізного вибору між вкладками (app/static/js/selection.js, F18) у Node без браузера.
import { test } from "node:test";
import assert from "node:assert/strict";

const sel = await import(new URL("../../app/static/js/selection.js", import.meta.url).href);

test("форма «Місії» → поля «Плану місії»", () => {
  assert.deepEqual(sel.planFieldsFromMission({ crewed: true, crew: 3, days: 14, systemId: "sls", trajectory: "low_energy" }),
    { profile: "crewed", vehicle: "sls", crew: 3, days: 14, trajectory: "low_energy" });
  assert.deepEqual(sel.planFieldsFromMission({ crewed: false, crew: 3, days: 14, systemId: "", trajectory: "?" }),
    { profile: "uncrewed", vehicle: "any" });
  assert.equal(sel.planFieldsFromMission(null), null);
  assert.equal(sel.planFieldsFromMission({ crewed: true, crew: 99 }).crew, undefined);
});

const response = {
  auto_selected: 2,
  plans: [
    { rank: 1, landing: { moon_site: { site_id: null, lat: -89, lon: 1 } }, launch: null },
    { rank: 2, landing: { moon_site: { site_id: "shackleton", lat: -89.9, lon: 0 } },
      launch: { site: { id: "kourou" }, vehicle: { id: "falcon-heavy" }, trajectory: "direct" } },
  ],
};

test("лідер плану — за auto_selected, а не за порядком; без запуску — порожні поля", () => {
  assert.deepEqual(sel.leadFromPlan(response),
    { siteId: "kourou", vehicleId: "falcon-heavy", trajectory: "direct", moon: { site: "shackleton", lat: -89.9, lon: 0 } });
  const noLaunch = sel.leadFromPlan({ auto_selected: 1, plans: [response.plans[0]] });
  assert.equal(noLaunch.siteId, null);
  assert.equal(sel.leadFromPlan({ plans: [] }), null);
});

test("вибір для «Вікна запуску»: план переважає «Місію»; без обох — нічого", () => {
  const lead = sel.leadFromPlan(response);
  assert.deepEqual(sel.launchChoice(lead, { siteId: "vandenberg", trajectory: "low_energy" }),
    { siteId: "kourou", trajectory: "direct", source: "plan" });
  assert.deepEqual(sel.launchChoice(null, { siteId: "vandenberg", trajectory: "low_energy" }),
    { siteId: "vandenberg", trajectory: "low_energy", source: "mission" });
  assert.deepEqual(sel.launchChoice(null, null), { siteId: null, trajectory: null, source: null });
});

test("сховище недоступне — не падаємо", () => {
  assert.equal(sel.loadLead(), null);
  assert.doesNotThrow(() => sel.saveLead({ siteId: "x" }));
});
