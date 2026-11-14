// Зоряне небо (app/static/js/starfield.js): математика орієнтації без DOM і WebGL.
// Запуск: node --test tests/js/test_starfield.mjs
import { test } from "node:test";
import assert from "node:assert/strict";

const sf = await import(new URL("../../app/static/js/starfield.js", import.meta.url).href);
const close = (a, b, eps = 1e-9) => assert.ok(Math.abs(a - b) < eps, `${a} ≠ ${b}`);
const closeVec = (a, b, eps = 1e-9) => a.forEach((x, i) => close(x, b[i], eps));
const DEG = Math.PI / 180;

test("raDec: осі ICRF", () => {
  assert.deepEqual(sf.raDec([1, 0, 0]), { ra: 0, dec: 0 });
  close(sf.raDec([0, 1, 0]).ra, 90);
  close(sf.raDec([-1, 0, 0]).ra, 180);
  close(sf.raDec([0, -1, 0]).ra, 270);
  close(sf.raDec([0, 0, 1]).dec, 90);
  close(sf.raDec([0, 0, -2]).dec, -90);
});

test("skyUv: 0h по центру, RA збільшується ліворуч, північ угорі (опис карти SVS 4851)", () => {
  assert.deepEqual(sf.skyUv([1, 0, 0]), { u: 0.5, v: 0.5 });
  close(sf.skyUv([0, 1, 0]).u, 0.25); // RA 90° — ліворуч від центру
  close(sf.skyUv([0, -1, 0]).u, 0.75); // RA 270° (−90°) — праворуч
  close(sf.skyUv([0, 0, 1]).v, 0); // північний полюс — верхній рядок
  close(sf.skyUv([0, 0, -1]).v, 1);
  // Сіріус (RA 101,287°, Dec −16,716°)
  const ra = 101.287 * DEG, dec = -16.716 * DEG;
  const { u, v } = sf.skyUv([Math.cos(dec) * Math.cos(ra), Math.cos(dec) * Math.sin(ra), Math.sin(dec)]);
  close(u, 0.5 - 101.287 / 360);
  close(v, 0.5 + 16.716 / 180);
});

test("mul3, transpose3, apply3, quatToMat3", () => {
  const id = sf.IDENTITY3;
  assert.deepEqual(sf.mul3(id, id), id);
  const rz90 = sf.quatToMat3([0, 0, Math.SQRT1_2, Math.SQRT1_2]); // поворот на 90° навколо z
  closeVec(sf.apply3(rz90, [1, 0, 0]), [0, 1, 0]);
  closeVec(sf.apply3(rz90, [0, 1, 0]), [-1, 0, 0]);
  sf.mul3(rz90, sf.transpose3(rz90)).forEach((row, i) => closeVec(row, id[i]));
  closeVec(sf.apply3(sf.quatToMat3([0, 0, 0, 1]), [3, 4, 5]), [3, 4, 5]);
});

test("cameraToIcrf: без поворотів камера дивиться вздовж −z; поворот сцени переходить у напрям ICRF", () => {
  closeVec(sf.apply3(sf.cameraToIcrf([0, 0, 0, 1], sf.IDENTITY3), [0, 0, -1]), [0, 0, -1]);
  const frame = sf.quatToMat3([0, 0, Math.SQRT1_2, Math.SQRT1_2]); // ICRF → сцена: поворот на 90° навколо z
  closeVec(sf.apply3(sf.cameraToIcrf([0, 0, 0, 1], frame), [1, 0, 0]), [0, -1, 0]); // сцена (1,0,0) = ICRF (0,−1,0)
});

test("ME_TO_GLOBE: (cosφ·sinλ, sinφ, cosφ·cosλ) із ME (cosφ·cosλ, cosφ·sinλ, sinφ)", () => {
  for (const [lat, lon] of [[0, 0], [30, 45], [-60, 120], [89, -170]]) {
    const la = lat * DEG, lo = lon * DEG;
    const me = [Math.cos(la) * Math.cos(lo), Math.cos(la) * Math.sin(lo), Math.sin(la)];
    closeVec(sf.apply3(sf.ME_TO_GLOBE, me), [Math.cos(la) * Math.sin(lo), Math.sin(la), Math.cos(la) * Math.cos(lo)]);
  }
});

test("meToSurface: схід, зеніт ME → осі сцени; матриця ортонормована", () => {
  const E = [1, 0, 0], N = [0, 0, -1], U = [0, 1, 0]; // осі сцени виду з поверхні (skyVector)
  for (const [lat, lon] of [[0, 0], [26.13, 3.63], [-89.67, 129.78], [45, -100]]) {
    const m = sf.meToSurface(lat, lon, E, N, U);
    const la = lat * DEG, lo = lon * DEG;
    closeVec(sf.apply3(m, [Math.cos(la) * Math.cos(lo), Math.cos(la) * Math.sin(lo), Math.sin(la)]), U);
    closeVec(sf.apply3(m, [-Math.sin(lo), Math.cos(lo), 0]), E);
    sf.mul3(m, sf.transpose3(m)).forEach((row, i) => closeVec(row, sf.IDENTITY3[i], 1e-12));
  }
});
