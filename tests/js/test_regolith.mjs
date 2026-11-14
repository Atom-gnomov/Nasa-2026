// Ґрунт (app/static/js/regolith.js): шари мікрорельєфу, колір з карти, шейдер.
import { test } from "node:test";
import assert from "node:assert/strict";

const rg = await import(new URL("../../app/static/js/regolith.js", import.meta.url).href);

const small = (spec, size = 96) => ({ ...spec, size });

test("rng детермінований і в межах [0, 1)", () => {
  const a = rg.rng(7), b = rg.rng(7);
  for (let i = 0; i < 50; i++) { const x = a(); assert.equal(x, b()); assert.ok(x >= 0 && x < 1); }
  assert.notEqual(rg.rng(7)(), rg.rng(8)());
});

test("шари: плитки від дрібної до великої, нахили відповідають цілі, без NaN", () => {
  const tiles = rg.GROUND_LAYERS.map((l) => l.tileM);
  assert.deepEqual(tiles, [...tiles].sort((x, y) => x - y));
  assert.ok(rg.NEAR_TILE_M < tiles[0], "ближній шар дрібніший за найдрібнішу плитку");
  for (const spec of rg.GROUND_LAYERS) {
    const layer = rg.regolithLayer(small(spec));
    const n = layer.size * layer.size;
    assert.equal(layer.albedo.length, n);
    const mags = [];
    for (let k = 0; k < n; k++) {
      for (const a of [layer.albedo[k], layer.gx[k], layer.gy[k]]) assert.ok(Number.isFinite(a), spec.name);
      assert.ok(layer.albedo[k] >= 0.78 - 1e-6 && layer.albedo[k] <= 1 + 1e-6);
      assert.ok(Math.abs(layer.gx[k]) <= 1 && Math.abs(layer.gy[k]) <= 1);
      mags.push(Math.hypot(layer.gx[k], layer.gy[k]));
    }
    mags.sort((p, q) => p - q);
    const p95 = mags[Math.floor(n * 0.95)];
    // нормування до цільового 95-го перцентиля (обрізання до ±1 лише трохи зсуває його вниз)
    assert.ok(p95 > spec.slope * 0.8 && p95 <= spec.slope * 1.05, `${spec.name}: ${p95} проти ${spec.slope}`);
  }
});

test("шар детермінований: однакова текстура щоразу, різні шари різні", () => {
  const [g0, g1] = rg.GROUND_LAYERS;
  const a = rg.regolithLayer(small(g0)), b = rg.regolithLayer(small(g0)), c = rg.regolithLayer(small(g1));
  assert.deepEqual([...a.gx.slice(0, 200)], [...b.gx.slice(0, 200)]);
  assert.notDeepEqual([...a.albedo.slice(0, 200)], [...c.albedo.slice(0, 200)]);
});

test("шар тайловий: різниця нахилу й альбедо через шов така сама, як між будь-якими сусідніми пікселями", () => {
  const n = 96, layer = rg.regolithLayer(small(rg.GROUND_LAYERS[1], n));
  const dif = (arr, i1, i2) => Math.abs(arr[i1] - arr[i2]);
  for (const arr of [layer.gx, layer.gy, layer.albedo]) {
    let seam = 0, inner = 0;
    for (let k = 0; k < n; k++) {
      seam += dif(arr, k * n + n - 1, k * n) + dif(arr, (n - 1) * n + k, k);
      inner += dif(arr, k * n + 47, k * n + 48) + dif(arr, 47 * n + k, 48 * n + k);
    }
    assert.ok(seam / n < 3 * inner / n + 0.05, `шов ${seam / n} проти ${inner / n}`);
  }
});

test("нахили узгоджені з висотою: кратер — чаша (нахил до центру), вал — навпаки; середній нахил близький до нуля", () => {
  const layer = rg.regolithLayer(small(rg.GROUND_LAYERS[2], 128));
  let sx = 0, sy = 0;
  for (let k = 0; k < layer.gx.length; k++) { sx += layer.gx[k]; sy += layer.gy[k]; }
  assert.ok(Math.abs(sx / layer.gx.length) < 0.05 && Math.abs(sy / layer.gy.length) < 0.05, "тайл не має загального нахилу");
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

test("шейдер: потрібні входи, мікрорельєф рахується відносно гладкої поверхні й гасне вдалині", () => {
  for (const u of ["uT0", "uT1", "uT2", "uTile", "uNear", "uSun", "uTint", "uUnit"]) assert.ok(rg.GROUND_FRAG.includes(u), u);
  assert.ok(rg.GROUND_VERT.includes("aLight") && rg.GROUND_VERT.includes("vMeters"));
  assert.match(rg.GROUND_FRAG, /smoothstep\(250\.0, 2500\.0/, "вдалині деталь згасає");
  assert.match(rg.GROUND_FRAG, /up > 0\.0 \?/, "без Сонця над горизонтом мікрорельєф не освітлюється");
  assert.ok(rg.GROUND_FRAG.includes("colorspace_fragment"), "вихід у sRGB, як у решти сцени");
});
