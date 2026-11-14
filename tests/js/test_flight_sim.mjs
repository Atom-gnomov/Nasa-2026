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
