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
