// Тести порівняння місць (app/static/js/compare.js) у Node без браузера: правила «краще значення».
// Запуск: node --test tests/js/test_compare.mjs (або pytest tests/test_state_js.py).
// Значення метрик нижче — довільні тестові входи в межах схеми SiteMetrics, не дані про реальні місця.
import { test } from "node:test";
import assert from "node:assert/strict";

const { ROWS, pickBetter, tableRows, compareUrl } = await import(new URL("../../app/static/js/compare.js", import.meta.url).href);
const row = (label) => {
  const r = ROWS.find((x) => x.label === label);
  assert.ok(r, `немає рядка «${label}»`);
  return r;
};

const station = (id, available) => ({ id, name: `${id} (DSN)`, moon_elevation_deg: 30, station_elevation_deg: 5, min_elevation_deg: 10, available });
function metrics(over = {}) {
  return {
    lat: 0, lon: 0, height_m: 0, datetime: "2027-07-01T00:00:00Z",
    sun_elevation_deg: 20, sun_azimuth_deg: 90, sun_visible_fraction: 1,
    earth_elevation_deg: 40, earth_azimuth_deg: 180, earth_visible_fraction: 1, earth_visible: true,
    earth_distance_km: 384400, signal_delay_s: 1.282, recommended_station: "madrid",
    hours_to_sunset: 100, hours_to_sunrise: 400, hours_to_earthset: null, hours_to_earthrise: null,
    event_search_hours: 720, local_solar_time_h: 9.5, sun_distance_km: 1.5e8,
    solar_irradiance_w_m2: 1361, panel_power_vertical_w_m2: 300, panel_power_horizontal_w_m2: 140,
    horizon_source: "flat",
    stations: [station("goldstone", false), station("madrid", true), station("canberra", false)],
    ...over,
  };
}

test("більше — краще для освітлення й потужності, менше — для затримки", () => {
  assert.equal(pickBetter(row("Сонце видно"), metrics({ sun_visible_fraction: 0.4 }), metrics({ sun_visible_fraction: 1 })), "b");
  assert.equal(pickBetter(row("Панель 1 м² вертикальна"), metrics({ panel_power_vertical_w_m2: 350 }), metrics()), "a");
  assert.equal(pickBetter(row("Затримка сигналу"), metrics({ signal_delay_s: 1.25 }), metrics({ signal_delay_s: 1.3 })), "a");
  assert.equal(pickBetter(row("Станцій DSN на зв'язку"), metrics(), metrics({ stations: [station("madrid", true), station("canberra", true)] })), "b");
});

test("довідкові рядки й рівні з точністю показу значення не виділяються", () => {
  assert.equal(pickBetter(row("Кут Сонця"), metrics({ sun_elevation_deg: 5 }), metrics({ sun_elevation_deg: 50 })), null);
  assert.equal(pickBetter(row("Місцевий сонячний час"), metrics({ local_solar_time_h: 1 }), metrics()), null);
  // 0,4 Вт різниці не видно при показі цілих ват — не виділяємо.
  assert.equal(pickBetter(row("Панель 1 м² вертикальна"), metrics({ panel_power_vertical_w_m2: 300.2 }), metrics({ panel_power_vertical_w_m2: 299.8 })), null);
  assert.equal(pickBetter(row("Затримка сигналу"), metrics({ signal_delay_s: 1.2821 }), metrics({ signal_delay_s: 1.2824 })), null);
});

test("захід і схід Сонця порівнюються лише для місць в однаковому стані", () => {
  const lit = (h) => metrics({ sun_visible_fraction: 1, hours_to_sunset: h });
  const dark = (h) => metrics({ sun_visible_fraction: 0, hours_to_sunrise: h, panel_power_vertical_w_m2: 0, panel_power_horizontal_w_m2: 0 });
  assert.equal(pickBetter(row("До заходу Сонця"), lit(50), lit(120)), "b");
  assert.equal(pickBetter(row("До сходу Сонця"), dark(50), dark(120)), "a");
  assert.equal(pickBetter(row("До заходу Сонця"), lit(50), dark(120)), null);
  assert.equal(pickBetter(row("До сходу Сонця"), lit(50), dark(120)), null);
});

test("подія поза вікном пошуку (null): захід «ніколи» — краще, схід «ніколи» — гірше", () => {
  assert.equal(pickBetter(row("До заходу Сонця"), metrics({ hours_to_sunset: null }), metrics({ hours_to_sunset: 300 })), "a");
  const dark = (h) => metrics({ sun_visible_fraction: 0, hours_to_sunrise: h });
  assert.equal(pickBetter(row("До сходу Сонця"), dark(null), dark(300)), "b");
  assert.equal(pickBetter(row("До заходу Сонця"), metrics({ hours_to_sunset: null }), metrics({ hours_to_sunset: null })), null);
  assert.equal(row("До заходу Сонця").text(metrics({ hours_to_sunset: null })), "немає за 30 діб");
});

test("захід і схід Землі — лише коли Землю видно (не видно) з обох місць", () => {
  const up = (h) => metrics({ earth_visible: true, hours_to_earthset: h });
  const down = (h) => metrics({ earth_visible: false, earth_visible_fraction: 0, hours_to_earthrise: h });
  assert.equal(pickBetter(row("До заходу Землі"), up(10), up(20)), "b");
  assert.equal(pickBetter(row("До сходу Землі"), down(10), down(20)), "a");
  assert.equal(pickBetter(row("До заходу Землі"), up(10), down(20)), null);
  assert.equal(pickBetter(row("Земля видна"), up(10), down(20)), "a");
});

test("затримка сигналу не порівнюється, якщо в одного місця немає зв'язку", () => {
  const noLink = metrics({ recommended_station: null, signal_delay_s: 1.2, stations: [station("madrid", false)] });
  assert.equal(pickBetter(row("Затримка сигналу"), noLink, metrics()), null);
  assert.equal(pickBetter(row("Станцій DSN на зв'язку"), noLink, metrics()), "b");
  assert.equal(row("Станцій DSN на зв'язку").text(noLink), "0 з 1");
  assert.equal(row("Станцій DSN на зв'язку").text(metrics()), "1 з 3 · madrid");
});

test("таблиця: усі рядки, формат показу за CONTRACTS §5.3", () => {
  const rows = tableRows(metrics({ horizon_source: "lola_20m", hours_to_sunset: 100.04 }), metrics({ sun_visible_fraction: 0.456 }));
  assert.deepEqual(rows.map((r) => r.label), ROWS.map((r) => r.label));
  const byLabel = Object.fromEntries(rows.map((r) => [r.label, r]));
  assert.equal(byLabel["Сонце видно"].b, "46 %");
  assert.equal(byLabel["Кут Сонця"].a, "20.00°");
  assert.equal(byLabel["До заходу Сонця"].a, "100 год (4.2 доби)");
  assert.equal(byLabel["Затримка сигналу"].a, "1.282 с");
  assert.equal(byLabel["Місцевий сонячний час"].a, "09:30");
  assert.equal(byLabel["Маска горизонту"].a, "LOLA LOLA_20M");
  assert.equal(byLabel["Маска горизонту"].b, "гладка сфера");
  for (const r of rows) for (const v of [r.a, r.b]) assert.doesNotMatch(v, /undefined|NaN/);
});

test("запит /api/compare: id місць повторюються параметром site, дата — datetime", () => {
  assert.equal(compareUrl(["apollo-11", "apollo-12"], "2027-07-01T10:00Z"), "/api/compare?site=apollo-11&site=apollo-12&datetime=2027-07-01T10%3A00Z");
});
