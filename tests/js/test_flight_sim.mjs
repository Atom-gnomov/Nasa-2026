// Тести симуляції польоту (G12) у app/static/js/flight.js — без браузера.
import { test } from "node:test";
import assert from "node:assert/strict";

const f = await import(new URL("../../app/static/js/flight.js", import.meta.url).href);

// Пряма дуга вздовж X: 7000 → 384400 км за 4 доби, швидкість падає 10 → 0,5 км/с
const traj = {
  points_km: [[7000, 0, 0], [100000, 0, 0], [384400, 0, 0]],
  times_s: [0, 86400, 345600],
  speeds_km_s: [10, 2, 0.5],
  moon_at_arrival_km: [384400, 0, 0],
};

test("стан на старті, посередині відрізка й у кінці", () => {
  const a = f.stateAt(traj, 0);
  assert.deepEqual(a.pos, [7000, 0, 0]);
  assert.equal(a.speedKmS, 10);
  assert.equal(a.progress, 0);
  const mid = f.stateAt(traj, 43200);
  assert.equal(mid.pos[0], 53500);
  assert.equal(mid.speedKmS, 6);
  assert.deepEqual(mid.dir, [1, 0, 0]);
  const end = f.stateAt(traj, 1e9);
  assert.ok(end.done && end.remainingS === 0 && end.progress === 1);
  assert.equal(end.distTargetKm, 0);
});

test("затримка зв'язку = відстань до Землі / c; залишок = повний час − пройдений", () => {
  const s = f.stateAt(traj, 86400);
  assert.ok(Math.abs(s.delayS - 100000 / f.LIGHT_KM_S) < 1e-9);
  assert.equal(s.remainingS, 345600 - 86400);
  assert.equal(s.distTargetKm, 284400);
});

test("без даних для анімації (старий сервер) — null й порожня панель", () => {
  assert.equal(f.stateAt({ points_km: traj.points_km }, 10), null);
  assert.deepEqual(f.telemetryRows(null), []);
});

test("рядки телеметрії — без undefined/NaN; тривалості читабельні", () => {
  for (const [name, value] of f.telemetryRows(f.stateAt(traj, 100000))) {
    assert.ok(name && !/undefined|NaN/.test(value), `${name}: ${value}`);
  }
  assert.equal(f.fmtDuration(90061), "1 д 1 год");
  assert.equal(f.fmtDuration(3720), "1 год 2 хв");
  assert.equal(f.fmtDuration(42), "42 с");
});

test("interpSystem: Місяць і Сонце інтерполюються між відліками", () => {
  const mk = (ms, x) => ({ ms, state: { datetime: new Date(ms).toISOString(), moon_km: [x, 0, 0], sun_km: [0, x, 0], moon_orientation: [[x, 0, 0], [0, 1, 0], [0, 0, 1]] } });
  const samples = [mk(0, 100), mk(3600000, 200), mk(7200000, 400)];
  const mid = f.interpSystem(samples, 1800000);
  assert.deepEqual(mid.moon_km, [150, 0, 0]);
  assert.deepEqual(mid.sun_km, [0, 150, 0]);
  assert.equal(mid.moon_orientation[0][0], 150);
  assert.equal(mid.datetime, samples[0].state.datetime); // обертання Землі екстраполює система
  assert.equal(f.interpSystem(samples, -5), samples[0].state);
  assert.equal(f.interpSystem(samples, 9e9), samples[2].state);
  assert.equal(f.interpSystem([], 0), null);
});

test("sampleTimes: щогодини від відльоту до прибуття включно", () => {
  const t = f.sampleTimes(0, 3 * 3600 + 1800);
  assert.deepEqual(t, [0, 3600000, 7200000, 10800000, 12600000]);
});

test("remapNearMoon: не заходить у кулю Місяця, неперервно на межі", () => {
  const r = 10;
  assert.equal(f.remapNearMoon(0, r), 13.5); // у центрі дуги — на висоті орбіти, а не в центрі
  assert.ok(f.remapNearMoon(5, r) > r);
  assert.equal(f.remapNearMoon(70, r), 70);
  assert.equal(f.remapNearMoon(500, r), 500);
  assert.ok(Math.abs(f.remapNearMoon(69.999, r) - 70) < 0.01);
});

test("descentState: від 100 км до 0 зі зникаючою швидкістю; рядки без NaN", () => {
  const a = f.descentState(0), z = f.descentState(1);
  assert.equal(a.altKm, 100);
  assert.ok(a.speedKmS > 1.6 && !a.landed);
  assert.equal(z.altKm, 0);
  assert.equal(z.speedKmS, 0);
  assert.ok(z.landed);
  assert.ok(f.descentState(0.5).altKm < 100 && f.descentState(0.5).altKm > 0);
  for (const p of [0, 0.3, 1]) for (const [n, v] of f.descentRows(p, "89° пд.")) assert.ok(n && !/undefined|NaN/.test(v));
  assert.equal(f.descentRows(1)[0][1], "Посадка виконана");
});

// ---------- G16: розгін TLI залежить від маси ----------
const burn = { duration_s: 600, accel_start_g: 0.35, accel_end_g: 0.71, mass_start_kg: 17000, mass_end_kg: 8400,
               utilization: 0.97, overloaded: false };

test("розгін: стан на початку, посередині й у кінці", () => {
  assert.ok(f.validBurn(burn) && !f.validBurn(null) && !f.validBurn({ duration_s: 0 }));
  const a = f.burnStateAt(burn, 0), mid = f.burnStateAt(burn, 0.5), end = f.burnStateAt(burn, 2);
  assert.equal(a.accelG, 0.35); assert.equal(a.remainingS, 600);
  assert.equal(mid.elapsedS, 300); assert.equal(mid.massKg, 12700);
  assert.ok(end.done && end.remainingS === 0 && end.accelG === 0.71);
});

test("телеметрія розгону: тривалість, прискорення, маса, заповненість; попередження про перевантаження", () => {
  const rows = f.burnRows(burn, 0.5);
  const byName = Object.fromEntries(rows);
  assert.equal(byName["Час розгону"], "5 хв 0 с");
  assert.match(byName["Прискорення"], /^0,53 g$/);
  assert.equal(byName["Заповненість ракети"], "97 %");
  assert.ok(!("Увага" in byName));
  assert.ok(f.burnRows({ ...burn, overloaded: true }, 0).some(([k]) => k === "Увага"));
  for (const [k, v] of rows) assert.ok(k && !/undefined|NaN/.test(v), `${k}: ${v}`);
});

test("підсумок розгону для перельоту; без даних — порожньо", () => {
  assert.deepEqual(f.burnSummaryRows(null), []);
  const rows = f.burnSummaryRows({ ...burn, overloaded: true });
  assert.equal(rows[0][0], "Розгін TLI");
  assert.match(rows[0][1], /10 хв 0 с, 0,35 → 0,71 g/);
  assert.match(rows[1][1], /97 % ⚠/);
});

test("важчий вантаж — довший розгін у даних бекенда: форма даних збігається з flight_phases", () => {
  const light = { ...burn, duration_s: 400, accel_start_g: 0.9 }, heavy = { ...burn, duration_s: 640, accel_start_g: 0.33 };
  assert.ok(f.burnStateAt(heavy, 0.5).elapsedS > f.burnStateAt(light, 0.5).elapsedS);
  assert.ok(f.burnStateAt(heavy, 0).accelG < f.burnStateAt(light, 0).accelG);
});

// ---------- G17: маршрут перельоту впливає на політ ----------
test("запит сцени: економний маршрут додає trajectory=low_energy, прямий — ні", () => {
  const direct = new URLSearchParams(f.flightUrl("kourou", Date.UTC(2027, 6, 1), -89, 0).split("?")[1]);
  assert.equal(direct.has("trajectory"), false);
  const slow = new URLSearchParams(f.flightUrl("kourou", Date.UTC(2027, 6, 1), -89, 0, "low_energy").split("?")[1]);
  assert.equal(slow.get("trajectory"), "low_energy");
});

test("інший маршрут — нове завантаження польоту, навіть якщо місце й час ті самі", () => {
  const prev = { siteId: "kourou", lat: -89, lon: 0, ms: 1e12, route: "direct" };
  assert.equal(f.needsReload(prev, { ...prev }), false);
  assert.equal(f.needsReload(prev, { ...prev, route: "low_energy" }), true);
  assert.equal(f.needsReload({ siteId: "kourou", lat: -89, lon: 0, ms: 1e12 }, { ...prev }), false); // без route = direct
});

test("швидкість симуляції за тривалістю перельоту: ≈ 20 с реальних; 105 діб — швидше, ніж 4 доби", () => {
  assert.equal(f.defaultSimSpeed(4 * 86400), 43200);   // 4 доби / 20 с = 4,8 год/с → 12 год/с
  assert.equal(f.defaultSimSpeed(105 * 86400), 259200); // 105 діб / 20 с → 3 доби/с
  assert.equal(f.defaultSimSpeed(0), 3600);
  assert.ok(f.defaultSimSpeed(105 * 86400) > f.defaultSimSpeed(4 * 86400));
});

test("відліки польоту: прямий — щогодини, економний 105 діб — рідше, але не більше ~168 відліків", () => {
  assert.equal(f.sampleStepMs(4.5 * 86400), 3600000);
  const long = f.sampleStepMs(105 * 86400);
  assert.ok(long > 3600000 && long % 3600000 === 0);
  const times = f.sampleTimes(0, 105 * 86400, long);
  assert.ok(times.length <= 170, String(times.length));
  assert.equal(times.at(-1), 105 * 86400 * 1000);
  assert.equal(f.sampleStepMs(0), 3600000);
});

test("час і політ: ▶ ставиться на паузу на час польоту й вмикається після нього", () => {
  let st = f.timeInitial();
  st = f.timeOnPlayPress(st); // ввімкнули час
  assert.deepEqual(st, { playing: true, resume: false, flight: false });
  st = f.timeOnFlightStart(st); // старт польоту: час на паузі, запам'ятали
  assert.deepEqual(st, { playing: false, resume: true, flight: true });
  st = f.timeOnFlightEnd(st); // посадка: час знову йде
  assert.deepEqual(st, { playing: true, resume: false, flight: false });
});

test("час і політ: час був вимкнений — після польоту лишається вимкненим; ▶ під час польоту — відкладене ввімкнення", () => {
  let st = f.timeOnFlightStart(f.timeInitial());
  assert.equal(st.resume, false);
  assert.deepEqual(f.timeOnFlightEnd(st), { playing: false, resume: false, flight: false });
  st = f.timeOnPlayPress(st); // натиснули ▶ під час польоту
  assert.deepEqual(st, { playing: false, resume: true, flight: true });
  assert.equal(f.timeOnPlayPress(st).resume, false, "повторне натискання скасовує");
  assert.equal(f.timeOnFlightEnd(st).playing, true);
});

// ---------- G17: маршрут перельоту впливає на політ ----------
test("запит сцени: економний маршрут додає trajectory=low_energy, прямий — ні", () => {
  const direct = new URLSearchParams(f.flightUrl("kourou", Date.UTC(2027, 6, 1), -89, 0).split("?")[1]);
  assert.equal(direct.has("trajectory"), false);
  const slow = new URLSearchParams(f.flightUrl("kourou", Date.UTC(2027, 6, 1), -89, 0, "low_energy").split("?")[1]);
  assert.equal(slow.get("trajectory"), "low_energy");
});

test("інший маршрут — нове завантаження польоту, навіть якщо місце й час ті самі", () => {
  const prev = { siteId: "kourou", lat: -89, lon: 0, ms: 1e12, route: "direct" };
  assert.equal(f.needsReload(prev, { ...prev }), false);
  assert.equal(f.needsReload(prev, { ...prev, route: "low_energy" }), true);
  assert.equal(f.needsReload({ siteId: "kourou", lat: -89, lon: 0, ms: 1e12 }, { ...prev }), false); // без route = direct
});

test("швидкість симуляції за тривалістю перельоту: ≈ 20 с реальних; 105 діб — швидше, ніж 4 доби", () => {
  assert.equal(f.defaultSimSpeed(4 * 86400), 43200);   // 4 доби / 20 с = 4,8 год/с → 12 год/с
  assert.equal(f.defaultSimSpeed(105 * 86400), 259200); // 105 діб / 20 с → 3 доби/с
  assert.equal(f.defaultSimSpeed(0), 3600);
  assert.ok(f.defaultSimSpeed(105 * 86400) > f.defaultSimSpeed(4 * 86400));
});

test("відліки польоту: прямий — щогодини, економний 105 діб — рідше, але не більше ~168 відліків", () => {
  assert.equal(f.sampleStepMs(4.5 * 86400), 3600000);
  const long = f.sampleStepMs(105 * 86400);
  assert.ok(long > 3600000 && long % 3600000 === 0);
  const times = f.sampleTimes(0, 105 * 86400, long);
  assert.ok(times.length <= 170, String(times.length));
  assert.equal(times.at(-1), 105 * 86400 * 1000);
  assert.equal(f.sampleStepMs(0), 3600000);
});

test("запит сцени: календар — дата посадки (anchor=arrival)", () => {
  const q = new URLSearchParams(f.flightUrl("kourou", Date.UTC(2027, 6, 10), -89, 0).split("?")[1]);
  assert.equal(q.get("anchor"), "arrival");
});

test("камера під маршрут: відстань = охоплення траси × запас; без траси — 0", () => {
  assert.equal(f.fitDistance(0), 0);
  assert.equal(f.fitDistance(NaN), 0);
  assert.equal(f.fitDistance(1900), 1900 * 3.4);
  assert.ok(f.fitDistance(1900) > 1100); // довша за типовий «Огляд» (1100) — кадр розширюється
  assert.ok(f.fitDistance(300) < 1100);  // прямий політ вміщується в типовий кадр
});

test("час сцени на розгоні йде до моменту відльоту; швидкість часу наростає плавно, без стрибка", () => {
  const t0 = Date.parse("2026-12-05T00:00:00Z");
  assert.equal(f.burnSceneMs(t0, 1), t0); // розгін закінчується відльотом
  assert.equal(f.burnSceneMs(t0, 0), t0 - f.BURN_LEAD_S * 1000);
  assert.ok(f.burnSceneMs(t0, 0.3) < f.burnSceneMs(t0, 0.6)); // час тече вперед, а не стоїть
  assert.equal(f.burnSceneMs(t0, 5), t0); // поза межами — затиснуто
  const from = f.burnTimeRate(), target = 86400;
  assert.equal(f.rampedSpeed(from, target, 0), from); // перелітний час стартує зі швидкості розгону
  assert.equal(f.rampedSpeed(from, target, f.TIME_RAMP_S), target);
  assert.equal(f.rampedSpeed(from, target, 99), target);
  let prev = from;
  for (let s = 0.25; s <= f.TIME_RAMP_S; s += 0.25) { // монотонно й без великих кроків між сусідніми кадрами
    const v = f.rampedSpeed(from, target, s);
    assert.ok(v >= prev && v - prev < (target - from) * 0.25, `s=${s}`);
    prev = v;
  }
});
