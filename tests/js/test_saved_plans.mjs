// Тести збережених планів (app/static/js/saved_plans.js, F30) у Node: сховище підміняється об'єктом у пам'яті.
import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";

const mem = new Map();
globalThis.localStorage = {
  getItem: (k) => (mem.has(k) ? mem.get(k) : null),
  setItem: (k, v) => { mem.set(k, String(v)); },
  removeItem: (k) => { mem.delete(k); },
};
beforeEach(() => mem.clear());

const sp = await import(new URL("../../app/static/js/saved_plans.js", import.meta.url).href);

const NOW = new Date("2026-11-15T10:00:00Z");
const snapshot = (over = {}) => ({
  mission: { crewed: true, days: 14, v: 2 }, plan: { name: "Південь", goal: "ice", confirmed: {} },
  launch: { site: "kourou", trajectory: "direct", vehicle: "any", departure: "", arrival: "" }, lead: null, search: null,
  state: { datetime: "2027-08-24T02:01Z", site: "shackleton", lat: -89.54, lon: 0 }, ...over,
});

test("знімок: читає всі сховища майстра й стан; відсутні — null", () => {
  mem.set("lse-mission", JSON.stringify({ crewed: true }));
  mem.set("lse-mission-plan", JSON.stringify({ name: "A" }));
  const snap = sp.snapshotNow({ datetime: "2027-01-01T00:00Z", site: null, lat: 1, lon: 2, extra: "не береться" });
  assert.deepEqual(snap.mission, { crewed: true });
  assert.equal(snap.plan.name, "A");
  assert.equal(snap.launch, null);
  assert.deepEqual(snap.state, { datetime: "2027-01-01T00:00Z", site: null, lat: 1, lon: 2 });
});

test("нормалізація знімка: лише відомі розділи, сміття відкидається, завеликий — ні", () => {
  const n = sp.normalizeSnapshot({ ...snapshot(), evil: { x: 1 }, mission: "рядок", state: { datetime: { a: 1 }, lat: 5, site: "s", lon: "x" } });
  assert.equal(n.mission, null);
  assert.equal("evil" in n, false);
  assert.deepEqual(n.state, { datetime: null, site: "s", lat: 5, lon: "x" });
  assert.equal(sp.normalizeSnapshot([]), null);
  assert.equal(sp.normalizeSnapshot({ mission: { big: "x".repeat(70000) } }), null);
});

test("збереження: нове — зверху, однойменне оновлюється, ліміт", () => {
  const a = sp.savePlanNow([], "Південь", snapshot(), NOW);
  assert.equal(a.replaced, false);
  assert.equal(a.plans[0].name, "Південь");
  assert.equal(a.entry.savedAt, NOW.toISOString());
  const b = sp.savePlanNow(a.plans, "Інший", snapshot(), NOW);
  assert.deepEqual(b.plans.map((p) => p.name), ["Інший", "Південь"]);
  const again = sp.savePlanNow(b.plans, " Південь ", snapshot({ plan: { name: "x", goal: "base", confirmed: {} } }), NOW);
  assert.equal(again.replaced, true);
  assert.equal(again.plans.length, 2);
  assert.equal(again.plans.find((p) => p.name === "Південь").id, a.entry.id);
  assert.equal(again.plans.find((p) => p.name === "Південь").data.plan.goal, "base");
  assert.equal(sp.savePlanNow([], "   ", snapshot(), NOW).entry.name, "Без назви");
  let full = [];
  for (let i = 0; i < sp.MAX_PLANS; i += 1) full = sp.savePlanNow(full, `план ${i}`, snapshot(), NOW).plans;
  assert.equal(sp.savePlanNow(full, "зайвий", snapshot(), NOW), null);
  assert.ok(sp.savePlanNow(full, "план 3", snapshot(), NOW).replaced); // оновити можна й при повному списку
});

test("копія для порівняння: унікальні імена, глибока копія, видалення", () => {
  const { plans } = sp.savePlanNow([], "Південь", snapshot(), NOW);
  const c1 = sp.duplicatePlan(plans, plans[0].id, NOW);
  assert.equal(c1.entry.name, "Південь (копія)");
  const c2 = sp.duplicatePlan(c1.plans, c1.entry.id, NOW);
  assert.equal(c2.entry.name, "Південь (копія 2)");
  c2.entry.data.mission.days = 99;
  assert.equal(plans[0].data.mission.days, 14);
  assert.notEqual(c1.entry.id, plans[0].id);
  assert.equal(sp.duplicatePlan(plans, "нема", NOW), null);
  assert.equal(sp.removePlan(c2.plans, c2.entry.id).length, 2);
});

test("зберігання у localStorage: круговий обхід і битий вміст", () => {
  const { plans } = sp.savePlanNow([], "Південь", snapshot(), NOW);
  sp.storePlans(plans);
  assert.deepEqual(sp.loadPlans().map((p) => p.name), ["Південь"]);
  mem.set(sp.PLANS_KEY, "не json");
  assert.deepEqual(sp.loadPlans(), []);
  mem.set(sp.PLANS_KEY, JSON.stringify([{ id: "a b", name: "x", data: snapshot() }, { id: "ok", name: "y", data: snapshot() }, 5]));
  assert.deepEqual(sp.loadPlans().map((p) => p.id), ["ok"]);
});

test("відкриття: розділи пишуться у сховища, відсутні прибираються", () => {
  mem.set("lse-plan-lead", JSON.stringify({ siteId: "старий" }));
  assert.equal(sp.applySnapshot(snapshot()), true);
  assert.equal(JSON.parse(mem.get("lse-mission")).days, 14);
  assert.equal(JSON.parse(mem.get("lse-mission-plan")).goal, "ice");
  assert.equal(mem.has("lse-plan-lead"), false); // у знімку lead = null
  assert.equal(sp.applySnapshot([]), false);
});

test("опис плану в списку", () => {
  const text = sp.describePlan({ data: sp.normalizeSnapshot(snapshot()) });
  assert.match(text, /пілотована/);
  assert.match(text, /14 діб/);
  assert.match(text, /Пошук води й льоду/);
  assert.match(text, /-89\.5°, 0\.0°/);
  assert.match(text, /2027-08-24/);
  assert.equal(sp.describePlan({ data: sp.normalizeSnapshot({}) }), "");
});

test("файл обміну: експорт → імпорт, нові id, перевірка вмісту", () => {
  const { plans } = sp.savePlanNow([], "Південь", snapshot(), NOW);
  const text = sp.exportFile(plans);
  const res = sp.parseImport(text);
  assert.equal(res.plans.length, 1);
  assert.equal(res.plans[0].name, "Південь");
  assert.notEqual(res.plans[0].id, plans[0].id);
  assert.match(sp.parseImport("не json").error, /не JSON/);
  assert.match(sp.parseImport(JSON.stringify({ version: 9, plans: [] })).error, /не схожий/);
  assert.match(sp.parseImport(JSON.stringify({ version: 1, plans: [5, null] })).error, /жодного дійсного/);
  assert.equal(sp.parseImport(JSON.stringify({ version: 1, plans: [{ name: "x", data: { mission: { a: 1 } } }, "сміття"] })).plans.length, 1);
});

test("злиття імпорту: однойменні отримують суфікс, ліміт рахується", () => {
  const base = sp.savePlanNow([], "Південь", snapshot(), NOW).plans;
  const imported = sp.parseImport(sp.exportFile(base)).plans;
  const merged = sp.mergeImported(base, imported);
  assert.deepEqual(merged.plans.map((p) => p.name), ["Південь (імпорт)", "Південь"]);
  const again = sp.mergeImported(merged.plans, sp.parseImport(sp.exportFile(base)).plans);
  assert.ok(again.plans.some((p) => p.name === "Південь (імпорт 2)"));
  let full = [];
  for (let i = 0; i < sp.MAX_PLANS; i += 1) full = sp.savePlanNow(full, `п${i}`, snapshot(), NOW).plans;
  const over = sp.mergeImported(full, imported);
  assert.equal(over.skipped, 1);
  assert.equal(over.plans.length, sp.MAX_PLANS);
});
