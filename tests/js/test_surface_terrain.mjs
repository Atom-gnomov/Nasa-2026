// Тести поверхні довкола точки (app/static/js/surface_terrain.js) у Node: сітка, освітлення, тіні, фаза Землі, панорама.
// Запуск: node --test tests/js/test_surface_terrain.mjs (або pytest tests/test_state_js.py).
// Усі поверхні нижче — синтетичні (площини, хребет, пагорб): це перевірка геометрії, а не дані про Місяць.
import { test } from "node:test";
import assert from "node:assert/strict";

const t = await import(new URL("../../app/static/js/surface_terrain.js", import.meta.url).href);
const R = t.R_MOON_M;
const DEG = Math.PI / 180;

// Ділянка n × n з кроком s, висоти f(e, n) — як у відповіді /api/terrain.
function patch(n, s, f = () => 0) {
  const c = (n - 1) / 2, h = new Float32Array(n * n);
  let hmin = Infinity, hmax = -Infinity;
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      const v = f((j - c) * s, (i - c) * s);
      h[i * n + j] = v;
      hmin = Math.min(hmin, v); hmax = Math.max(hmax, v);
    }
  }
  return { n, s, c, half: c * s, h, hmin, hmax };
}

test("сітка з API: base64 float32 little-endian → висоти", () => {
  const src = new Float32Array([0, 1.5, -2.25, 1000.125, 7, 8, 9, 10, -11]);
  const b64 = Buffer.from(src.buffer).toString("base64");
  assert.deepEqual([...t.decodeHeights(b64, 3)], [...src]);
  assert.throws(() => t.decodeHeights(b64, 4), /очікується/);
  const p = t.makePatch({ n: 3, spacing_m: 100, heights_b64: b64 });
  assert.equal(p.c, 1);
  assert.equal(p.half, 100);
  assert.equal(p.hmin, -11);
  assert.equal(p.hmax, 1000.125);
});

test("білінійна висота точна на площині, NaN поза ділянкою", () => {
  const p = patch(41, 10, (e, n) => 2 * e + 3 * n);
  for (const [e, n] of [[0, 0], [37.3, -12.1], [-199.9, 150.2], [200, 200]]) {
    assert.ok(Math.abs(t.heightAt(p, e, n) - (2 * e + 3 * n)) < 1e-3, `${e}/${n}`);
  }
  assert.ok(Number.isNaN(t.heightAt(p, 200.5, 0)));
  assert.ok(Number.isNaN(t.heightAt(p, 0, -201)));
});

test("кроки променя: густо поблизу (≈ 3,4 %), не рідше за крок сітки далеко, кривина в sin/cos", () => {
  const { dist, sinD, cosD } = t.terrainSteps(patch(301, 33.3));
  assert.ok(dist[0] === 3 && dist.at(-1) <= 5000 * 0.98 + 1e-9 && dist.at(-1) > 4800);
  for (let k = 1; k < dist.length; k++) {
    const dd = dist[k] - dist[k - 1];
    assert.ok(dd > 0 && dd <= 33.3 + 1e-9 && dd <= dist[k - 1] * 0.0341 + 1e-9, `крок ${k}: ${dd}`);
  }
  assert.ok(dist.length > 250 && dist.length < 400, dist.length);
  for (const k of [0, 100, dist.length - 1]) assert.ok(Math.abs(sinD[k] ** 2 + cosD[k] ** 2 - 1) < 1e-12);
  assert.ok(Math.abs(cosD.at(-1) - (1 - dist.at(-1) ** 2 / (2 * R ** 2))) < 1e-9, "5 км: cos δ ≈ 1 − d²/2R²");
});

test("освітлення: плоска поверхня = sin(висоти Сонця), нижче горизонту — темрява", () => {
  const p = patch(61, 20);
  const at = (az, el) => t.lightGrid(p, az, el, { shadows: false })[30 * 61 + 30];
  assert.ok(Math.abs(at(40, 30) - 0.5) < 2e-3);
  assert.ok(Math.abs(at(200, 75) - Math.sin(75 * DEG)) < 2e-3);
  assert.equal(at(0, -5), 0);
  assert.ok(at(0, 0.2) < 0.01);
  assert.equal(t.lightGrid(p, 0, -45).reduce((a, b) => a + b, 0), 0);
});

test("освітлення: схил до Сонця світліший, від Сонця — темніший (кут між нормаллю й Сонцем)", () => {
  const a = Math.tan(10 * DEG);
  const west = patch(61, 20, (e) => a * e); // росте на схід: схил дивиться на захід
  const east = patch(61, 20, (e) => -a * e); // спадає на схід: дивиться на схід
  const at = (p, az, el) => t.lightGrid(p, az, el, { shadows: false })[30 * 61 + 30];
  assert.ok(Math.abs(at(west, 90, 30) - Math.sin(20 * DEG)) < 3e-3, "Сонце на сході, схил від нього");
  assert.ok(Math.abs(at(east, 90, 30) - Math.sin(40 * DEG)) < 3e-3, "Сонце на сході, схил до нього");
  assert.ok(Math.abs(at(east, 270, 30) - Math.sin(20 * DEG)) < 3e-3, "Сонце на заході — навпаки");
});

test("тіні: за хребтом у бік від Сонця — тінь завдовжки h / tg(висоти Сонця), перед ним — світло", () => {
  // хребет на схід від центра: e = 500…520 м, висота 200 м; Сонце на сході, 10° → тінь ≈ 1134 м на захід
  const p = patch(401, 10, (e) => (e >= 500 && e <= 520 ? 200 : 0));
  const lit = t.lightGrid(p, 90, 10, { shadows: true });
  const plain = t.lightGrid(p, 90, 10, { shadows: false });
  const cell = (g, e, n = 0) => g[Math.round(200 + n / 10) * 401 + Math.round(200 + e / 10)];
  const sun10 = Math.sin(10 * DEG);
  assert.equal(cell(lit, 0), 0, "e = 0: промінь на хребті на 88 м, хребет 200 м");
  assert.equal(cell(lit, 300), 0);
  assert.ok(Math.abs(cell(plain, 0) - sun10) < 2e-3, "без тіней там світло");
  assert.ok(Math.abs(cell(lit, -800) - sun10) < 2e-3, "e = −800: промінь на хребті на 229 м > 200 м — світло");
  assert.ok(Math.abs(cell(lit, 700) - sun10) < 2e-3, "східніше хребта — сторона Сонця");
  assert.ok(Math.abs(cell(lit, 510) - sun10) < 0.15, "верх хребта освітлений");
  const shadowEdge = [...Array(120).keys()].map((k) => -k * 10).find((e) => cell(lit, e) > 0);
  assert.ok(shadowEdge <= 500 - 1134 + 40 && shadowEdge >= 500 - 1134 - 40, `межа тіні на ${shadowEdge} м, очікується ≈ −634 м`);
});

test("крок lattice (stride) дає ту саму тінь у межах крок-блока", () => {
  const p = patch(201, 10, (e) => (e >= 300 && e <= 320 ? 150 : 0));
  const full = t.lightGrid(p, 90, 8, { stride: 1 });
  const coarse = t.lightGrid(p, 90, 8, { stride: 4 });
  let diff = 0;
  for (let k = 0; k < full.length; k++) if ((full[k] === 0) !== (coarse[k] === 0)) diff++;
  assert.ok(diff / full.length < 0.01, `розбіжність ${diff} з ${full.length}`);
});

test("фаза Землі: Сонце й Земля в одному напрямку — нова, у протилежних — повна, під 90° — половина", () => {
  assert.ok(Math.abs(t.earthPhase(120, 30, 120, 30).fraction) < 1e-9);
  assert.ok(Math.abs(t.earthPhase(0, 20, 180, -20).fraction - 1) < 1e-9);
  const q = t.earthPhase(90, 0, 0, 0);
  assert.ok(Math.abs(q.fraction - 0.5) < 1e-9 && Math.abs(q.elongation - 90) < 1e-9);
  assert.ok(Math.abs(q.bearing - 90) < 1e-9, "Сонце праворуч від Землі → освітлений край праворуч");
  assert.ok(Math.abs(t.earthPhase(0, 40, 0, 10).bearing - 0) < 1e-9, "Сонце прямо над Землею → освітлений верх");
  assert.ok(Math.abs(t.earthPhase(0, 10, 0, 40).bearing - 180) < 1e-9, "Сонце під Землею → низ");
  assert.ok(Math.abs(t.earthPhase(270, 0, 0, 0).bearing - 270) < 1e-9);
});

function frame(W, H) { return { width: W, height: H, pixels: new Uint32Array(W * H) }; }
const firstRow = (f, x) => { for (let y = 0; y < f.height; y++) if (f.pixels[y * f.width + x]) return y; return -1; };

test("панорама, гладка сфера: межа землі на геометричному горизонті (−√(2h/R)), нижче — суцільно земля", () => {
  const p = patch(301, 33.3);
  const f = frame(360, 180);
  t.renderTerrain(p, new Float32Array(p.n * p.n).fill(0.5), { ...f, viewAz: 0, viewEl: 0, fov: 90, eye: 2 });
  const dip = Math.atan(Math.sqrt((2 * 2) / R)) / DEG; // ≈ 0,087°
  for (const x of [0, 90, 180, 300, 359]) {
    const y0 = firstRow(f, x);
    assert.ok(Math.abs(y0 - (90 + dip * 4)) <= 1.5, `x=${x}: ${y0}`);
    for (let y = y0; y < 180; y++) assert.ok(f.pixels[y * 360 + x], `порожнеча на ${x}/${y}`);
  }
});

test("панорама: пагорб на сході видно на висоті, що збігається з аналітичним кутом (з кривиною)", () => {
  const p = patch(301, 33.3, (e, n) => 150 * Math.exp(-((e - 2000) ** 2 + n ** 2) / (2 * 100 ** 2)));
  const f = frame(360, 180);
  t.renderTerrain(p, new Float32Array(p.n * p.n).fill(0.5), { ...f, viewAz: 90, viewEl: 0, fov: 90, eye: 2 });
  const d = 2000, rho = Math.hypot(R, d);
  const el = Math.atan2((R + 150) * R / rho - R - 2, (R + 150) * d / rho) / DEG; // ≈ 4,2°
  assert.ok(el > 4 && el < 4.4, el);
  const y0 = firstRow(f, 180);
  assert.ok(Math.abs(y0 - (90 - el * 4)) <= 2, `верхівка в рядку ${y0}, очікується ≈ ${(90 - el * 4).toFixed(1)}`);
  assert.ok(firstRow(f, 0) > 85, "на заході (az 45°…) землі вище горизонту немає");
});

test("панорама: масштаб — висота рельєфу ×N піднімає силует (вертикальне перебільшення)", () => {
  const p = patch(301, 33.3, (e, n) => 150 * Math.exp(-((e - 2000) ** 2 + n ** 2) / (2 * 100 ** 2)));
  const view = { viewAz: 90, viewEl: 0, fov: 90, eye: 2 };
  const a = frame(360, 180), b = frame(360, 180);
  const light = new Float32Array(p.n * p.n).fill(0.5);
  t.renderTerrain(p, light, { ...a, ...view, exag: 1 });
  t.renderTerrain(p, light, { ...b, ...view, exag: 3 });
  assert.ok(firstRow(b, 180) < firstRow(a, 180) - 20, `${firstRow(b, 180)} проти ${firstRow(a, 180)}`);
});

test("панорама: за межами ділянки — силует за маскою горизонту, лише там, де маска вища", () => {
  const p = patch(301, 33.3);
  const mask = { azimuth_step_deg: 1, elevations_deg: Array.from({ length: 360 }, (_, i) => (i >= 80 && i <= 100 ? 1.5 : -0.5)) };
  const f = frame(360, 180);
  t.renderTerrain(p, new Float32Array(p.n * p.n), { ...f, viewAz: 90, viewEl: 0, fov: 90, mask, farLight: 0 });
  assert.ok(Math.abs(firstRow(f, 180) - Math.floor(90 - 1.5 * 4)) <= 1, "на 90°: хребет 1,5° → рядок 84");
  assert.ok(Math.abs(firstRow(f, 0) - 90) <= 1.5, "на 45°: маска нижча за горизонт — лише земля ділянки");
});

test("панорама без ділянки: лише маска; без маски — гладка земля нижче горизонту", () => {
  const mask = { azimuth_step_deg: 1, elevations_deg: Array(360).fill(2) };
  const a = frame(360, 180);
  t.renderTerrain(null, null, { ...a, viewAz: 0, viewEl: 0, fov: 90, mask });
  assert.ok(Math.abs(firstRow(a, 100) - 82) <= 1);
  const b = frame(360, 180);
  t.renderTerrain(null, null, { ...b, viewAz: 0, viewEl: 0, fov: 90 });
  assert.equal(firstRow(b, 100), 90);
});

test("яскравість: монотонна, земне сяйво дає темну, але не чорну ніч", () => {
  const g = [0, 0.25, 0.5, 1].map((v) => t.shadeGray(v));
  assert.deepEqual([...g].sort((a, b) => a - b), g);
  assert.ok(t.shadeGray(0) > 0 && t.shadeGray(0) < 20 && t.shadeGray(1) > 200 && t.shadeGray(5) === 255);
});

test("кільця дальності: на ґрунті з'являється рядок кольору кільця на відстані кільця й повертається його положення", () => {
  const p = patch(301, 33.3, (e, n) => 0);
  const f = frame(360, 180);
  const light = new Float32Array(p.n * p.n).fill(0.5);
  const { ringRows } = t.renderTerrain(p, light, { ...f, viewAz: 0, viewEl: 0, fov: 90, eye: 2, rings: [10, 100] });
  const row = (d) => ringRows.find((r) => r.d === d)?.y;
  assert.ok(row(10) > row(100) && row(100) >= 90, "ближче — нижче в кадрі");
  const expected = (d) => 90 - Math.atan2(R * R / Math.hypot(R, d) - R - 2, d) / DEG * 4; // el = −atan((h_ока + падіння)/d)
  // кільце стоїть на першому вузлі променя після відстані кільця; вузли йдуть з кроком 3,4 % → допуск 4 рядки
  assert.ok(Math.abs(row(10) - expected(10)) <= 4 && Math.abs(row(100) - expected(100)) <= 2, `${row(10)} / ${row(100)}`);
  const ring = f.pixels[row(10) * 360 + 180], ground = f.pixels[(row(10) + 3) * 360 + 180];
  assert.notEqual(ring, ground);
  const none = frame(360, 180);
  assert.equal(t.renderTerrain(p, light, { ...none, viewAz: 0, viewEl: 0, fov: 90 }).ringRows.length, 0);
});
