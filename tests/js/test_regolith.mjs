// Текстура реголіту (app/static/js/regolith.js): детермінованість, тайлінг, діапазон, колір ґрунту.
import { test } from "node:test";
import assert from "node:assert/strict";

const rg = await import(new URL("../../app/static/js/regolith.js", import.meta.url).href);

test("rng детермінований і в межах [0, 1)", () => {
  const a = rg.rng(7), b = rg.rng(7);
  for (let i = 0; i < 50; i++) { const x = a(); assert.equal(x, b()); assert.ok(x >= 0 && x < 1); }
  assert.notEqual(rg.rng(7)(), rg.rng(8)());
});

test("regolithMap: розмір, діапазон 0,55…1, середнє яскраве, та сама текстура щоразу", () => {
  const m = rg.regolithMap(128, 1), m2 = rg.regolithMap(128, 1);
  assert.equal(m.length, 128 * 128);
  assert.deepEqual([...m.slice(0, 64)], [...m2.slice(0, 64)]);
  let lo = Infinity, hi = -Infinity, sum = 0;
  for (const v of m) { lo = Math.min(lo, v); hi = Math.max(hi, v); sum += v; }
  assert.ok(Math.abs(lo - 0.55) < 1e-6 && Math.abs(hi - 1) < 1e-6);
  const mean = sum / m.length;
  assert.ok(mean > 0.6 && mean < 0.9, `середнє ${mean}`);
});

test("regolithMap тайлова: різниця через шов не більша за звичайну різницю сусідів", () => {
  const n = 128, m = rg.regolithMap(n, 3);
  let seam = 0, inner = 0;
  for (let k = 0; k < n; k++) {
    seam += Math.abs(m[k * n + n - 1] - m[k * n]);
    inner += Math.abs(m[k * n + 63] - m[k * n + 64]);
  }
  assert.ok(seam / n < 3 * inner / n + 0.05, `шов ${seam / n} проти ${inner / n}`);
});

test("tintFromRgb: сірий не фарбується; теплий — тепліший; межі 0,8…1,25; чорний — без відтінку", () => {
  assert.deepEqual(rg.tintFromRgb(120, 120, 120), [1, 1, 1]);
  const [r, g, b] = rg.tintFromRgb(140, 120, 100);
  assert.ok(r > 1 && b < 1 && r > g && g > b);
  for (const c of rg.tintFromRgb(255, 0, 0, 5)) assert.ok(c >= 0.8 && c <= 1.25);
  assert.deepEqual(rg.tintFromRgb(0, 0, 0), [1, 1, 1]);
});

test("moonMapPixel: довгота 0° по центру, північ угорі, краї", () => {
  assert.deepEqual(rg.moonMapPixel(2000, 1000, 0, 0), { x: 1000, y: 500 });
  assert.deepEqual(rg.moonMapPixel(2000, 1000, 90, 0), { x: 1000, y: 0 });
  assert.deepEqual(rg.moonMapPixel(2000, 1000, -90, 0), { x: 1000, y: 999 });
  assert.equal(rg.moonMapPixel(2000, 1000, 0, -180).x, 0);
  assert.equal(rg.moonMapPixel(2000, 1000, 0, 180).x, 0);
  assert.equal(rg.moonMapPixel(2000, 1000, 0, 90).x, 1500);
});
