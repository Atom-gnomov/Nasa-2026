// Тести геометрії виду «з поверхні» (app/static/js/surface_geometry.js) у Node без браузера.
// Запуск: node --test tests/js/test_surface.mjs (або pytest tests/test_state_js.py).
// Маски й ряди нижче — довільні тестові входи в межах схем HorizonMask / Timeline.
import { test } from "node:test";
import assert from "node:assert/strict";

const s = await import(new URL("../../app/static/js/surface_geometry.js", import.meta.url).href);
const close = (a, b, eps = 1e-9) => a.every((v, i) => Math.abs(v - b[i]) < eps);

test("напрямки: північ = −z, схід = +x, зеніт = +y; азимут за годинниковою стрілкою", () => {
  assert.ok(close(s.skyVector(0, 0), [0, 0, -1]));
  assert.ok(close(s.skyVector(90, 0), [1, 0, 0]));
  assert.ok(close(s.skyVector(180, 0), [0, 0, 1]));
  assert.ok(close(s.skyVector(270, 0), [-1, 0, 0]));
  assert.ok(close(s.skyVector(123, 90), [0, 1, 0]));
  for (const [az, el] of [[0, 0], [45, 10], [200, -5], [359.5, 60]]) {
    const back = s.vectorToAzEl(s.skyVector(az, el));
    assert.ok(Math.abs(back.az - az) < 1e-9 && Math.abs(back.el - el) < 1e-9, `${az}/${el}`);
  }
});

test("справжні кутові діаметри: Сонце ≈ 0,533°, Земля з Місяця ≈ 1,90°", () => {
  assert.ok(Math.abs(s.SUN_DIAMETER_DEG - 0.533) < 0.001, s.SUN_DIAMETER_DEG);
  assert.ok(Math.abs(s.EARTH_DIAMETER_DEG - 1.901) < 0.001, s.EARTH_DIAMETER_DEG);
  assert.ok(Math.abs(s.angularDiameterDeg(1, 1) - 90) < 1e-9);
});

const mask = { azimuth_step_deg: 90, elevations_deg: [1, 2, 3, 4] };

test("профіль маски замкнений, інтерполяція між азимутами й через 360°", () => {
  assert.deepEqual(s.horizonProfile(mask), { az: [0, 90, 180, 270, 360], el: [1, 2, 3, 4, 1] });
  assert.equal(s.maskAt(mask, 45), 1.5);
  assert.equal(s.maskAt(mask, 315), 2.5, "між 270° (4) і 360° = 0° (1)");
  assert.equal(s.maskAt(mask, -45), 2.5);
  assert.equal(s.maskAt(mask, 720 + 90), 2);
});

test("шлях розривається на переході 360° → 0°", () => {
  assert.deepEqual(s.splitAtWrap([350, 355, 2, 8, 359, 1]), [[0, 2], [2, 4], [4, 5], [5, 6]]);
  assert.deepEqual(s.splitAtWrap([10, 20, 30]), [[0, 3]]);
  assert.deepEqual(s.splitAtWrap([]), []);
});

test("події: кроків до зміни видимості й підпис «до заходу / сходу»", () => {
  const vis = [true, true, true, false, false];
  assert.equal(s.stepsToChange(vis, 0), 3);
  assert.equal(s.stepsToChange(vis, 3), null);
  assert.equal(s.eventText("Сонця", vis, 0, 1), "над горизонтом, до заходу Сонця 3.0 год");
  assert.equal(s.eventText("Сонця", vis, 3, 1), "під горизонтом, до сходу Сонця — немає до кінця періоду");
  assert.equal(s.eventText("Землі", [false, false, true], 0, 24), "під горизонтом, до сходу Землі 2.0 доби");
});

test("межі розгортки: горизонт 0° і рельєф у межах, глибоко під горизонтом не розширює шкалу", () => {
  const pole = s.panoramaRange({ elevations_deg: [9.6, 0.5, -0.2] }, { sun: [-1.5, 1.6], earth: [-6.8, 6.9] });
  assert.deepEqual(pole, { min: -10, max: 10, step: 5 });
  const equator = s.panoramaRange({ elevations_deg: [0.4, 1.2] }, { sun: [-76, 88], earth: [59, 60] });
  assert.equal(equator.min, -30, "Сонце на −76° не тягне шкалу до −90°");
  assert.equal(equator.max, 90);
});

test("сторони світу: 8 підписів; на самому полюсі — від меридіана 0°", () => {
  assert.equal(s.compassLabels(0.67).length, 8);
  assert.deepEqual(s.compassLabels(0.67)[2], { az: 90, text: "Сх" });
  assert.deepEqual(s.compassLabels(-90).map((l) => l.text), ["0° від мерид. 0°", "90° від мерид. 0°", "180° від мерид. 0°", "270° від мерид. 0°"]);
  assert.equal(s.compassLabels(-89.5).length, 8, "поблизу полюса північ визначена");
});
