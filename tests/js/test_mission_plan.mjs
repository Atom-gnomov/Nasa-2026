// Тести навігації-майстра (app/static/js/mission_plan.js, F21) у Node без браузера.
import { test } from "node:test";
import assert from "node:assert/strict";

const m = await import(new URL("../../app/static/js/mission_plan.js", import.meta.url).href);

const ctx = (patch = {}) => ({
  plan: m.normalizePlan(null), mission: { crewed: true, crew: 2, days: 14, sizes: { equipment: 1, life_support: 1, comfort: 1 } },
  search: { days: 20, regionKey: "pole", minSunHours: 0, minCommHours: 0, maxSlopeDeg: 0, minEarthPct: 0, minSunPct: 0,
            priorities: [{ id: "energy", on: true }, { id: "comms", on: false }] },
  launch: { site: "kourou", vehicle: "any", trajectory: "direct" }, lead: null,
  state: { datetime: "2027-03-01T12:00Z", lat: -89.5, lon: 0, site: null }, ...patch,
});

test("є 10 кроків у порядку рішень; кроки 9–10 ще не готові", () => {
  assert.deepEqual(m.STEPS.map((s) => s.n), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  assert.deepEqual(m.STEPS.filter((s) => !s.ready).map((s) => s.n), [9, 10]);
  assert.equal(m.nextStep(8), null);   // далі лише готові кроки
  assert.equal(m.nextStep(3), 4);
  assert.equal(m.prevStep(1), null);
  assert.equal(m.prevStep(5), 4);
});

test("план: назва обрізається, мета з переліку, підтвердження лише для кроків 1–10", () => {
  const p = m.normalizePlan({ name: "x".repeat(200), goal: "teleport", confirmed: { 3: "a", 99: "b", x: "c", 5: 7 } });
  assert.equal(p.name.length, 80);
  assert.equal(p.goal, "");
  assert.deepEqual(p.confirmed, { 3: "a" });
  assert.equal(m.normalizePlan({ goal: "ice" }).goal, "ice");
});

test("стан кроку: todo → done після підтвердження → review після зміни даних", () => {
  const c = ctx();
  assert.equal(m.stepStatus(7, c), "todo");
  const confirmed = ctx({ plan: m.confirmStep(7, c) });
  assert.equal(m.stepStatus(7, confirmed), "done");
  const changed = ctx({ plan: confirmed.plan, mission: { ...c.mission, sizes: { equipment: 3, life_support: 1, comfort: 1 } } });
  assert.equal(m.stepStatus(7, changed), "review");
  assert.equal(m.stepStatus(2, changed), "todo"); // інші кроки не зачеплено
});

test("зміна однієї вимоги «Підбору» робить «Район і точка» потребуючим перегляду, а не «Тип місії»", () => {
  let c = ctx();
  c = ctx({ plan: m.confirmStep(2, c) });
  c = ctx({ plan: m.confirmStep(5, c) });
  assert.equal(m.stepStatus(5, c), "done");
  const next = { ...c, search: { ...c.search, maxSlopeDeg: 10 } };
  assert.equal(m.stepStatus(5, next), "review");
  assert.equal(m.stepStatus(2, next), "done");
  const moved = { ...c, state: { ...c.state, lat: -85 } };
  assert.equal(m.stepStatus(5, moved), "review");
});

test("дата календаря впливає на вікно запуску (3), але не на екіпаж (6)", () => {
  const c = ctx();
  const c3 = ctx({ plan: m.confirmStep(3, c) });
  const both = ctx({ plan: m.confirmStep(6, c3) });
  const later = { ...both, state: { ...both.state, datetime: "2027-04-01T12:00Z" } };
  assert.equal(m.stepStatus(3, later), "review");
  assert.equal(m.stepStatus(6, later), "done");
});

test("заповненість: мета, точка на Місяці, майданчик, розміри навантаження", () => {
  const c = ctx();
  assert.equal(m.stepFilled(1, c), false);
  assert.equal(m.stepFilled(1, ctx({ plan: { ...c.plan, goal: "ice" } })), true);
  assert.equal(m.stepFilled(5, ctx({ state: { datetime: "2027-03-01T12:00Z", lat: null, lon: null } })), false);
  assert.equal(m.stepFilled(8, ctx({ launch: {}, lead: { siteId: "kourou" } })), true);
  assert.equal(m.stepFilled(8, ctx({ launch: {}, lead: null })), false);
  assert.equal(m.stepFilled(2, ctx({ mission: null })), false);
  assert.equal(m.stepFilled(9, c), false);
});

test("крок за адресою: явний ?step=, інакше типовий для сторінки", () => {
  assert.equal(m.stepFromLocation("/mission", "?datetime=x&step=7"), 7);
  assert.equal(m.stepFromLocation("/mission", ""), 2);
  assert.equal(m.stepFromLocation("/plan", ""), 8);
  assert.equal(m.stepFromLocation("/system", ""), 8);
  assert.equal(m.stepFromLocation("/launch-window", ""), 3);
  assert.equal(m.stepFromLocation("/moon", "", "#search"), 5);
  assert.equal(m.stepFromLocation("/moon", "", ""), null);
  assert.equal(m.stepFromLocation("/mission", "?step=99"), 2);
});

test("адреса кроку зберігає дату й мову і додає step; Підбір — із #search", () => {
  const step5 = m.STEPS.find((s) => s.n === 5), step7 = m.STEPS.find((s) => s.n === 7);
  assert.equal(m.stepHref(step7, "?datetime=2027-03-01T12:00Z&lang=en"), "/mission?datetime=2027-03-01T12%3A00Z&lang=en&step=7");
  assert.equal(m.stepHref(step5, ""), "/search?step=5#search");
  assert.equal(m.stepHref(step7, "?step=2"), "/mission?step=7");
});

test("«Мій план»: лише заповнені поля; майданчик «оптимальний» для auto", () => {
  const rows = Object.fromEntries(m.summaryRows(ctx({ plan: { name: "Шеклтон-1", goal: "ice", confirmed: {} } })));
  assert.equal(rows["Назва"], "Шеклтон-1");
  assert.equal(rows["Мета"], "Пошук води й льоду");
  assert.equal(rows["Тип"], "пілотована");
  assert.equal(rows["Екіпаж"], "2 осіб, 14 діб");
  assert.equal(rows["Точка посадки"], "-89.50°, 0.00°");
  assert.equal(rows["Майданчик"], "kourou");
  assert.equal(Object.fromEntries(m.summaryRows(ctx({ launch: { site: "auto:fuel:any" } })))["Майданчик"], "оптимальний");
  assert.deepEqual(m.summaryRows({ plan: m.normalizePlan(null), state: {}, launch: {} }), []);
});
