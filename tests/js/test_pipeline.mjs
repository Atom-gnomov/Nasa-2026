// Тести єдиного конвеєра вибору між вкладками (app/static/js/pipeline.js, F20) у Node без браузера.
import { test } from "node:test";
import assert from "node:assert/strict";

const p = await import(new URL("../../app/static/js/pipeline.js", import.meta.url).href);
const search = await import(new URL("../../app/static/js/search.js", import.meta.url).href);

test("політ: нормалізація — некоректне відкидається, «оптимально» і майданчик допустимі", () => {
  assert.deepEqual(p.normalizeLaunch(null), { site: "", trajectory: "any", vehicle: "any" });
  assert.equal(p.normalizeLaunch({ site: "kourou" }).site, "kourou");
  assert.equal(p.normalizeLaunch({ site: "auto:fuel:spaceports" }).site, "auto:fuel:spaceports");
  assert.equal(p.normalizeLaunch({ site: "<script>", trajectory: "teleport", vehicle: "a b" }).site, "");
  assert.equal(p.normalizeLaunch({ trajectory: "teleport" }).trajectory, "any");
  assert.equal(p.normalizeLaunch({ vehicle: "ariane-64" }).vehicle, "ariane-64");
});

test("політ: конкретний майданчик відрізняється від «оптимально»; явний вибір переважає лідера плану", () => {
  assert.equal(p.plainSite("kourou"), "kourou");
  assert.equal(p.plainSite("auto:fuel:any"), null);
  assert.equal(p.plainSite(""), null);
  const lead = { siteId: "vandenberg", trajectory: "low_energy" };
  assert.equal(p.effectiveSite({ site: "kourou" }, lead), "kourou");
  assert.equal(p.effectiveSite({ site: "" }, lead), "vandenberg");
  assert.equal(p.effectiveSite({ site: "" }, null), "");
  assert.equal(p.effectiveTrajectory({ trajectory: "direct" }, lead), "direct");
  assert.equal(p.effectiveTrajectory({ trajectory: "any" }, lead), "low_energy");
  assert.equal(p.effectiveTrajectory({ trajectory: "any" }, null), "direct");
});

test("сховище недоступне — не падаємо, повертаємо типове", () => {
  assert.deepEqual(p.loadLaunch(), { site: "", trajectory: "any", vehicle: "any" });
  assert.doesNotThrow(() => p.saveLaunch({ site: "kourou" }));
  assert.equal(p.loadSearchForm(), null);
});

test("вимоги з «Підбору» → короткий опис без порожніх полів", () => {
  const form = { ...structuredClone(search.DEFAULT_FORM), days: 20, minSunHours: 100, maxSlopeDeg: 8, minEarthPct: 30,
                 priorities: [{ id: "comms", on: true }, { id: "energy", on: true }, { id: "radiation", on: false }] };
  const rows = Object.fromEntries(p.requirementsSummary(form));
  assert.equal(rows["Період"], "20 діб");
  assert.match(rows["Мін. годин Сонця"], /100/);
  assert.equal(rows["Макс. нахил"], "8°");
  assert.equal(rows["Мін. частка Землі (м'яка)"], "30 %");
  assert.equal(rows["Пріоритети"], "Зв'язок › Енергія"); // назви факторів, а не ідентифікатори
  assert.ok(!("Мін. годин зв'язку" in rows) && !("Мін. частка Сонця (м'яка)" in rows));
  assert.deepEqual(p.requirementsSummary(null), []);
});

test("вимоги «Підбору» потрапляють у запит плану без поля limit", () => {
  const form = { ...structuredClone(search.DEFAULT_FORM), days: 10, maxSlopeDeg: 12, minSunPct: 40 };
  const body = p.planRequirements(form, "2027-03-01T00:00Z");
  assert.equal(body.max_slope_deg, 12);
  assert.equal(body.min_sun_fraction, 0.4);
  assert.ok(!("limit" in body));
  assert.deepEqual(body.region, { lat_min: -90, lat_max: -80 });
});


test("вимоги: вибрана на кроці 5 точка показується замість області пошуку", () => {
  const form = { ...structuredClone(search.DEFAULT_FORM), days: 20 };
  const rows = Object.fromEntries(p.requirementsSummary(form, { lat: -82, lon: 28.8 }));
  assert.equal(rows["Точка посадки (крок 5)"], "-82.00°, 28.80°");
  assert.ok(!("Область" in rows));
  assert.ok("Область" in Object.fromEntries(p.requirementsSummary(form)));
});

test("перебування після посадки: з «Місії» для пілотованої, інакше 7 діб; межі 1…60", () => {
  assert.equal(p.stayDays({ crewed: true, days: 14 }), 14);
  assert.equal(p.stayDays({ crewed: true, days: 500 }), 60);
  assert.equal(p.stayDays({ crewed: true, days: 0 }), 7);
  assert.equal(p.stayDays({ crewed: false, days: 14 }), 7);
  assert.equal(p.stayDays(null), 7);
});

test("дата старту й прибуття в спільний вибір польоту не потрапляють (старту дата завжди від посадки)", () => {
  const out = p.normalizeLaunch({ site: "kourou", departure: "2027-03-02", arrival: "2027-03-06T14:22:00Z" });
  assert.deepEqual(out, { site: "kourou", trajectory: "any", vehicle: "any" });
});
