// Тести графіків таймлайну (app/static/js/charts.js) у Node без браузера: ряди, шкали, підписи.
// Запуск: node --test tests/js/test_charts.mjs (або pytest tests/test_state_js.py).
// Значення нижче — довільні тестові входи в межах схеми Timeline, не дані про реальні місця.
import { test } from "node:test";
import assert from "node:assert/strict";

const c = await import(new URL("../../app/static/js/charts.js", import.meta.url).href);

function timeline(n, { stepH = 1, sun = () => 5, earth = () => 3, avail = () => [true, false, false] } = {}) {
  const t0 = Date.UTC(2027, 6, 1, 0, 0);
  const times = Array.from({ length: n }, (_, i) => new Date(t0 + i * stepH * 3_600_000).toISOString().replace(".000Z", "Z"));
  const track = (f) => ({
    azimuth_deg: times.map(() => 0),
    elevation_deg: times.map((_, i) => f(i)),
    visible_fraction: times.map((_, i) => (f(i) > 0 ? 1 : 0)),
  });
  const ids = ["goldstone", "madrid", "canberra"];
  return {
    times,
    sun: track(sun),
    earth: track(earth),
    stations: ids.map((id, k) => ({ station_id: id, moon_elevation_deg: times.map(() => 20), available: times.map((_, i) => avail(i)[k]) })),
  };
}

test("місячна доба — синодичний місяць з calendar.js", () => {
  assert.equal(c.PERIOD_H, 29.530589 * 24);
});

test("timelineSeries: моменти в мс, кути, видимість і станції на зв'язку", () => {
  const s = c.timelineSeries(timeline(3, { avail: (i) => [i === 0, i === 0, false] }));
  assert.equal(s.t[1] - s.t[0], 3_600_000);
  assert.deepEqual(s.sun, [5, 5, 5]);
  assert.deepEqual(s.comm, [["goldstone", "madrid"], [], []]);
  assert.deepEqual(s.earthVisible, [1, 1, 1]);
});

test("шкала кутів: ±90° → крок 45°, біля полюса ±7° → 5°; горизонт 0° завжди в межах", () => {
  const equator = c.timelineSeries(timeline(4, { sun: (i) => [-90, 0, 90, 10][i], earth: () => 60 }));
  const r1 = c.elevationRange(equator);
  assert.deepEqual(r1, { min: -90, max: 90, step: 45 });
  assert.deepEqual(c.angleTicks(r1), [-90, -45, 0, 45, 90]);
  const pole = c.timelineSeries(timeline(4, { sun: (i) => [-1.5, 1.6, 0.2, -0.3][i], earth: (i) => [-6.8, 6.9, 0, 3][i] }));
  const r2 = c.elevationRange(pole);
  assert.deepEqual(r2, { min: -10, max: 10, step: 5 });
  const above = c.timelineSeries(timeline(2, { sun: () => 30, earth: () => 40 }));
  assert.ok(c.elevationRange(above).min <= 0, "0° у межах, навіть коли обидва тіла високо");
});

test("підписи дат: кожні 5 діб за місячну добу, щодня — за короткий період", () => {
  const month = c.timelineSeries(timeline(709));
  assert.deepEqual(c.dateTickIndices(month), [0, 120, 240, 360, 480, 600]);
  const twoDays = c.timelineSeries(timeline(49));
  assert.deepEqual(c.dateTickIndices(twoDays), [0, 24, 48]);
  assert.deepEqual(c.dateTickIndices(c.timelineSeries(timeline(1))), [0]);
});

test("курсор: частка ширини → найближчий момент, за межами — край", () => {
  const s = c.timelineSeries(timeline(11));
  assert.equal(c.indexAt(s, 0), 0);
  assert.equal(c.indexAt(s, 0.5), 5);
  assert.equal(c.indexAt(s, 1.4), 10);
  assert.equal(c.indexAt(s, -0.3), 0);
});

test("рядок під курсором: момент UTC, кути з видимістю, станції DSN", () => {
  const s = c.timelineSeries(timeline(2, { sun: () => -1.234, earth: () => 6.5, avail: (i) => [false, i === 1, i === 1] }));
  assert.equal(c.readout(s, 0), "01.07 00:00 UTC · Сонце -1.23° (видно 0 %) · Земля 6.50° (видно 100 %) · DSN: немає зв'язку");
  assert.equal(c.readout(s, 1), "01.07 01:00 UTC · Сонце -1.23° (видно 0 %) · Земля 6.50° (видно 100 %) · DSN: Madrid, Canberra");
});
