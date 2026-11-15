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

test("є 10 кроків; крок 3 злито з кроком 5, «Тривалість» і «Екіпаж» лише для пілотованої місії", () => {
  assert.deepEqual(m.STEPS.map((s) => s.n), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  assert.deepEqual(m.STEPS.filter((s) => !s.ready).map((s) => s.n), []);
  const crewed = { crewed: true }, uncrewed = { crewed: false };
  assert.deepEqual(m.visibleSteps(uncrewed).map((s) => s.n), [1, 2, 5, 7, 8, 9, 10]);
  assert.deepEqual(m.visibleSteps(crewed).map((s) => s.n), [1, 2, 4, 5, 6, 7, 8, 9, 10]);
  assert.deepEqual(m.visibleSteps(null).map((s) => s.n), [1, 2, 5, 7, 8, 9, 10]);
  assert.equal(m.displayNumber(5, uncrewed), 3);
  assert.equal(m.displayNumber(5, crewed), 4);
  assert.equal(m.displayNumber(4, uncrewed), 0); // прихований крок номера не має
  assert.equal(m.nextStep(2, uncrewed), 5);
  assert.equal(m.nextStep(2, crewed), 4);
  assert.equal(m.nextStep(4, crewed), 5);
  assert.equal(m.nextStep(3, uncrewed), 7); // 3 — псевдонім 5; крок 6 без людей прихований
  assert.equal(m.prevStep(7, uncrewed), 5);
  assert.equal(m.nextStep(8), 9);
  assert.equal(m.nextStep(9), 10);
  assert.equal(m.nextStep(10), null);
  assert.equal(m.prevStep(1), null);
  assert.equal(m.prevStep(5, uncrewed), 2);
  assert.equal(m.prevStep(5, crewed), 4);
  assert.equal(m.canonicalStep(3), 5);
  assert.equal(m.canonicalStep(7), 7);
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
  assert.equal(m.stepFilled(5, ctx({ state: { datetime: "2027-03-01T12:00Z", lat: -89.5, lon: 0 } })), true);
  assert.equal(m.stepFilled(5, ctx({ state: { datetime: "", lat: -89.5, lon: 0 } })), false); // без дати крок не заповнений
  assert.equal(m.stepFilled(8, ctx({ launch: {}, lead: { siteId: "kourou" } })), true);
  assert.equal(m.stepFilled(8, ctx({ launch: {}, lead: null })), false);
  assert.equal(m.stepFilled(2, ctx({ mission: null })), false);
  assert.equal(m.stepFilled(9, c), true);
  assert.equal(m.stepFilled(10, c), true);
});

test("крок за адресою: явний ?step=, інакше типовий для сторінки", () => {
  assert.equal(m.stepFromLocation("/mission", "?datetime=x&step=7"), 7);
  assert.equal(m.stepFromLocation("/mission", ""), 2);
  assert.equal(m.stepFromLocation("/plan", ""), 8);
  assert.equal(m.stepFromLocation("/system", ""), 8);
  assert.equal(m.stepFromLocation("/moon", "?step=3"), 5); // дата посадки злита з районом і точкою
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

test("фокус на кроці: елемент ховається, якщо він не для кроку й у ньому немає вкладених для кроку", () => {
  assert.equal(m.stepMatches("2 4 6", 4), true);
  assert.equal(m.stepMatches("2 4 6", 7), false);
  assert.equal(m.stepMatches(undefined, 1), false);
  assert.equal(m.stepMatches("10", 1), false); // 1 не збігається з 10
  assert.equal(m.hiddenInFocus("7", false, 2), true);       // чужий крок
  assert.equal(m.hiddenInFocus("2 4 6", false, 4), false);  // свій крок
  assert.equal(m.hiddenInFocus("2 4 6", true, 7), false);   // контейнер із потрібним вкладеним елементом лишається
  assert.equal(m.hiddenInFocus("2", false, 6), true);
});

// ---------- F22: мета → типові вибори наступних кроків ----------
const goalIce = { id: "ice", defaults: { mission_profile: "uncrewed", stay_days: 100, priorities: ["comms", "energy"] } };
const goalSamples = { id: "samples", defaults: { mission_profile: "crewed", stay_days: 7, priorities: ["energy", "comms", "radiation"] } };

test("мета «лід» → безпілотна, 100 діб, пріоритети зв'язок › енергія; решта факторів вимкнено, порядок збережено", () => {
  const out = m.applyGoalDefaults(goalIce, { crewed: true, crew: 3, days: 14, useBio: true, members: [{}] },
    { days: 20, regionKey: "pole", priorities: [{ id: "energy", on: true }, { id: "comms", on: true }, { id: "radiation", on: true }, { id: "temperature", on: false }] });
  assert.equal(out.mission.crewed, false);
  assert.equal(out.mission.days, 100);
  assert.equal(out.mission.crew, null);
  assert.equal(out.mission.useBio, false);
  assert.deepEqual(out.search.priorities.map((p) => `${p.id}:${p.on}`), ["comms:true", "energy:true", "radiation:false", "temperature:false"]);
  assert.equal(out.search.days, 20);            // решту полів «Підбору» не чіпаємо
  assert.equal(out.search.regionKey, "pole");
  assert.equal(out.changes.length, 3);
  assert.match(out.changes[1], /100/);
});

test("мета «зразки» → пілотована, 7 діб; без збережених форм — створює мінімальні й повні пріоритети", () => {
  const out = m.applyGoalDefaults(goalSamples, null, null);
  assert.equal(out.mission.crewed, true);
  assert.equal(out.mission.days, 7);
  assert.deepEqual(out.search.priorities.map((p) => p.id), ["energy", "comms", "radiation", "temperature"]);
  assert.deepEqual(out.search.priorities.map((p) => p.on), [true, true, true, false]);
  assert.match(out.changes[0], /пілотована/);
});

test("без мети (порожній вибір) нічого не змінюється", () => {
  const mission = { crewed: true, days: 14 }, search = { days: 30 };
  const out = m.applyGoalDefaults(null, mission, search);
  assert.equal(out.mission, mission);
  assert.equal(out.search, search);
  assert.deepEqual(out.changes, []);
});
