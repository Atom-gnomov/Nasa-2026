// Тести кроку 9 «Перевірка узгодженості» (app/static/js/consistency.js) у Node без браузера.
import { test } from "node:test";
import assert from "node:assert/strict";

const c = await import(new URL("../../app/static/js/consistency.js", import.meta.url).href);
const plan = await import(new URL("../../app/static/js/mission_plan.js", import.meta.url).href);

const state = { datetime: "2027-08-24T02:01Z", lat: -89.5, lon: 0 };

test("запит: дата, точка, назва й мета зі спільних сховищ; безпілотна — тривалість за типовою", () => {
  const body = c.buildConsistencyRequest({ state, plan: { name: "Південь", goal: "ice" } });
  assert.equal(body.datetime, state.datetime);
  assert.deepEqual(body.site, { lat: -89.5, lon: 0 });
  assert.equal(body.goal, "ice");
  assert.equal(body.name, "Південь");
  assert.equal(body.mission.mission_profile, "uncrewed");
  assert.equal(body.stay_days, 7);
  assert.equal(body.mission.trajectory, "direct");
});

test("запит: без точки site = null, без дати поля немає; пілотована бере тривалість із форми", () => {
  const body = c.buildConsistencyRequest({ missionRaw: { crewed: true, days: 21, v: 2 }, state: {} });
  assert.equal(body.site, null);
  assert.equal("datetime" in body, false);
  assert.equal(body.stay_days, 21);
  assert.equal(body.mission.mission_profile, "crewed");
});

test("запит: вибір польоту з «Вікна» й «Плану» переважає форму «Місії»", () => {
  const body = c.buildConsistencyRequest({
    missionRaw: { trajectory: "direct", systemId: "ariane-64" },
    launch: { site: "kourou", trajectory: "low_energy", vehicle: "sls-block-1" }, state,
  });
  assert.equal(body.mission.trajectory, "low_energy");
  assert.equal(body.mission.launch_system_id, "sls-block-1");
  assert.equal(body.mission.launch_site_id, "kourou");
  const auto = c.buildConsistencyRequest({ launch: { site: "auto:fuel:any", trajectory: "any", vehicle: "any" }, state });
  assert.equal("launch_site_id" in auto.mission, false); // «оптимально» — не конкретний майданчик
});

test("найдовша ніч зі «Місії» потрапляє в запит розрахунку", () => {
  const raw = c.withNight({ crewed: true, v: 2 }, 300);
  assert.equal(raw.nightH, 300);
  assert.equal(c.buildConsistencyRequest({ missionRaw: raw, state }).mission.longest_night_h, 300);
});

test("підсумок і рядки конфліктів із кроком майстра", () => {
  assert.match(c.summaryText({ counts: { error: 0, warning: 0, info: 0 } }), /не знайдено/);
  const resp = { counts: { error: 1, warning: 2, info: 0 }, conflicts: [
    { id: "a", severity: "error", step: 6, message: "Запасів не вистачає" },
    { id: "b", severity: "warning", step: 8, message: "Дві ракети" },
  ] };
  const text = c.summaryText(resp);
  assert.match(text, /1 — місія не виконується/);
  assert.match(text, /2 — варто виправити/);
  const rows = c.conflictRows(resp);
  assert.deepEqual(rows.map((r) => [r.icon, r.step, r.stepTitle]), [["✗", 6, "Екіпаж або техніка"], ["!", 8, "Носій і політ"]]);
  assert.equal(c.summaryText(null), "");
});

test("період перевірки: підпис із відсотками й ніччю", () => {
  const text = c.windowText({ start: "2027-08-27T02:01Z", end: "2027-09-03T02:01Z", sun_fraction: 0.62, earth_fraction: 0.5, longest_night_h: 12.4 });
  assert.match(text, /2027-08-27 02:01 UTC/);
  assert.match(text, /62 %/);
  assert.match(text, /12 год/);
  assert.equal(c.windowText(null), "");
});

test("майстер: крок 9 доступний, стає «потребує перегляду», коли змінились вибори кроків 1–8", () => {
  const step9 = plan.STEPS.find((s) => s.n === 9);
  assert.equal(step9.ready, true);
  assert.equal(step9.path, "/consistency");
  assert.equal(plan.stepFromLocation("/consistency"), 9);
  const ctx = { plan: { name: "", goal: "", confirmed: {} }, mission: { crewed: false, days: 14 }, state: { datetime: "2027-08-24T02:01Z", lat: -89, lon: 0 }, launch: {} };
  assert.equal(plan.stepStatus(9, ctx), "todo");
  const confirmed = plan.confirmStep(9, ctx);
  assert.equal(plan.stepStatus(9, { ...ctx, plan: confirmed }), "done");
  const changed = { ...ctx, plan: confirmed, state: { ...ctx.state, lat: -85 } };
  assert.equal(plan.stepStatus(9, changed), "review");
  assert.equal(plan.stepFilled(9, ctx), true);
});
