// Тести режимів якості 3D і 2D-заглушки без WebGL (app/static/js/three/quality.js, fallback2d.js) у Node.
// Запуск: node --test tests/js/test_quality.mjs (або pytest tests/test_state_js.py).
import { test } from "node:test";
import assert from "node:assert/strict";

const q = await import(new URL("../../app/static/js/three/quality.js", import.meta.url).href);
const f = await import(new URL("../../app/static/js/three/fallback2d.js", import.meta.url).href);

class MemoryStorage {
  constructor(init = {}) { this.data = new Map(Object.entries(init)); }
  getItem(k) { return this.data.has(k) ? this.data.get(k) : null; }
  setItem(k, v) { this.data.set(k, String(v)); }
}

test("за замовчуванням — «низька» (VISION, М16), некоректне значення теж дає «низька»", () => {
  assert.equal(q.getQuality(new MemoryStorage()), "low");
  assert.equal(q.getQuality(new MemoryStorage({ "lse-quality": "ultra" })), "low");
  assert.equal(q.getQuality(new MemoryStorage({ "lse-quality": "toString" })), "low", "лише власні ключі QUALITY");
  assert.equal(q.getQuality({ getItem() { throw new Error("SecurityError"); } }), "low", "приватний режим");
  assert.equal(q.getQuality(undefined), "low");
});

test("вибір зберігається на пристрої й читається назад", () => {
  const s = new MemoryStorage();
  assert.equal(q.setQuality("high", s), true);
  assert.equal(q.getQuality(s), "high");
  assert.equal(q.setQuality("ultra", s), false);
  assert.equal(q.getQuality(s), "high", "некоректний вибір не перезаписує збережений");
  assert.equal(q.setQuality("low", { setItem() { throw new Error("quota"); } }), true, "помилка сховища не ламає вибір");
});

test("«низька» не вантажить полярні тайли й не робить надвибірки; «висока» — навпаки", () => {
  const low = q.qualitySettings("low");
  const high = q.qualitySettings("high");
  assert.equal(low.polarTiles, false);
  assert.equal(low.pixelRatioMax, 1);
  assert.equal(low.antialias, false);
  assert.equal(high.polarTiles, true);
  assert.ok(high.pixelRatioMax > low.pixelRatioMax);
  assert.ok(high.anisotropyMax > low.anisotropyMax);
  assert.equal(q.qualitySettings("ultra"), low);
});

test("?webgl=0 вмикає 2D-заглушку (діагностика)", () => {
  assert.equal(q.webglDisabledByUrl("?webgl=0"), true);
  assert.equal(q.webglDisabledByUrl("?datetime=2027-07-01T00:00Z&webgl=0"), true);
  assert.equal(q.webglDisabledByUrl("?webgl=1"), false);
  assert.equal(q.webglDisabledByUrl(""), false);
});

test("перемикач якості: варіанти, поточне значення, зміна зберігає й перезавантажує", () => {
  globalThis.Option = class { constructor(text, value) { this.text = text; this.value = value; } };
  const storage = new MemoryStorage();
  const prev = globalThis.localStorage;
  Object.defineProperty(globalThis, "localStorage", { configurable: true, writable: true, value: storage });
  try {
    let handler = null;
    const select = {
      options: [], value: "",
      replaceChildren(...opts) { this.options = opts; },
      addEventListener(type, fn) { if (type === "change") handler = fn; },
    };
    let reloads = 0;
    q.mountQualitySelect(select, { reload: () => { reloads += 1; } });
    assert.deepEqual(select.options.map((o) => [o.value, o.text]), [["low", "низька"], ["high", "висока"]]);
    assert.equal(select.value, "low");
    select.value = "high";
    handler();
    assert.equal(storage.getItem("lse-quality"), "high");
    assert.equal(reloads, 1);
    q.mountQualitySelect(null); // немає елемента на сторінці — нічого не робить
  } finally {
    Object.defineProperty(globalThis, "localStorage", { configurable: true, writable: true, value: prev });
    delete globalThis.Option;
  }
});

test("2D-карта: точка ↔ частки карти (ліворуч −180°, угорі +90°, як текстура глобуса)", () => {
  assert.deepEqual(f.latLonToFraction(90, -180), { x: 0, y: 0 });
  assert.deepEqual(f.latLonToFraction(0, 0), { x: 0.5, y: 0.5 });
  assert.deepEqual(f.latLonToFraction(-90, 90), { x: 0.75, y: 1 });
  assert.deepEqual(f.latLonToFraction(0, 190), f.latLonToFraction(0, -170), "довгота нормалізується");
  assert.deepEqual(f.fractionToLatLon(0.5, 0.5), { lat: 0, lon: 0 });
  assert.deepEqual(f.fractionToLatLon(-0.2, 1.3), { lat: -90, lon: -180 }, "клік за межами притискається до краю");
  // Apollo 11 (каталог app/data/sites.json): туди й назад з точністю округлення 0,001°
  const { x, y } = f.latLonToFraction(0.67416, 23.47314);
  const back = f.fractionToLatLon(x, y);
  assert.ok(Math.abs(back.lat - 0.67416) <= 0.0005 && Math.abs(back.lon - 23.47314) <= 0.0005, JSON.stringify(back));
});
