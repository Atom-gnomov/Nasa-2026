// Тести модуля польоту в 3D-виді (app/static/js/flight.js, G9) у Node без браузера.
// Запуск: node --test tests/js/test_flight.mjs (або pytest tests/test_state_js.py).
import { test } from "node:test";
import assert from "node:assert/strict";

const f = await import(new URL("../../app/static/js/flight.js", import.meta.url).href);
const ms = Date.UTC(2027, 6, 1);

test("запит сцени з польотом", () => {
  assert.equal(f.flightUrl("", ms), null);
  const q = new URLSearchParams(f.flightUrl("kourou", ms, -85, 0).split("?")[1]);
  assert.equal(q.get("launch_site"), "kourou");
  assert.equal(q.get("datetime"), "2027-07-01T00:00:00Z");
  assert.equal(q.get("markers"), "0");
  assert.equal(q.get("lat"), "-85");
  assert.equal(new URLSearchParams(f.flightUrl("kourou", ms).split("?")[1]).get("lat"), null);
});

test("підпис польоту", () => {
  const extras = [
    { kind: "rocket", name: "Куру (Гвіанський космічний центр)" },
    { kind: "trajectory", launch_site_id: "kourou", departure_utc: "2027-07-01T00:00:00Z", arrival_utc: "2027-07-05T12:00:00Z",
      tof_days: 4.5, dv_tli_m_s: 3128.8, dv_loi_m_s: 845.2, windows_per_day: 2 },
  ];
  const text = f.flightFact(extras);
  assert.match(text, /^Куру: TLI 01\.07 00:00 → прибуття 05\.07 12:00 UTC/);
  assert.match(text, /3129 м\/с/);
  assert.match(text, /точку посадки не вибрано/);
  assert.equal(f.flightFact([]), "не вибрано майданчик старту");
});

test("перезапит лише коли змінилось щось суттєве", () => {
  const a = { siteId: "kourou", ms, lat: -85, lon: 0 };
  assert.equal(f.needsReload(null, a), true);
  assert.equal(f.needsReload(a, { ...a, ms: ms + 3600000 }), false);
  assert.equal(f.needsReload(a, { ...a, ms: ms + 7 * 3600000 }), true);
  assert.equal(f.needsReload(a, { ...a, siteId: "baikonur" }), true);
  assert.equal(f.needsReload(a, { ...a, lat: -80 }), true);
});

test("оптимальні варіанти: значення списку → параметри запиту", () => {
  assert.equal(f.AUTO_OPTIONS.length, 4);
  assert.deepEqual(f.parseFlightValue("auto:speed:any"), { siteId: "auto", criterion: "speed", scope: "any" });
  assert.deepEqual(f.parseFlightValue("kourou"), { siteId: "kourou", criterion: null, scope: null });
  assert.equal(f.parseFlightValue(""), null);
  const q = new URLSearchParams(f.flightUrl("auto:fuel:spaceports", ms, -85, 0).split("?")[1]);
  assert.equal(q.get("launch_site"), "auto");
  assert.equal(q.get("criterion"), "fuel");
  assert.equal(q.get("launch_scope"), "spaceports");
});

test("підсумок вибору: найкращий і альтернативи", () => {
  const opt = (id, name, wait, dv, extra = {}) => ({
    site: { id, name, lat: 0, lon: 91.9 }, wait_h: wait, dv_total_m_s: dv, inclination_deg: 20.4,
    dv_site_penalty_m_s: 29.3, arrival_utc: "2027-07-05T12:44:00Z", note: "примітка", ...extra,
  });
  const choice = { kind: "launch_choice", criterion: "fuel", scope: "spaceports",
    best: opt("kourou", "Куру (ELA-4)", 0.75, 4002.8), alternatives: [opt("alcantara", "Алкантара", 1.3, 4002.7)] };
  const text = f.choiceFact([choice]);
  assert.match(text, /^Оптимально \(паливо, космодроми\) — Куру: очікування 0,8 год, Δv 4003 м\/с/);
  assert.match(text, /Далі: Алкантара/);
  assert.equal(f.choiceFact([]), "—");
  const any = { ...choice, scope: "any", best: opt("any-point", "Довільна точка: вузол на екваторі", 0, 4002.8), alternatives: [] };
  assert.match(f.choiceFact([any]), /старт одразу/);
  assert.match(f.choiceFact([any]), /91,9°/);
});
