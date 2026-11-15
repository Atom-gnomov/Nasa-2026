// Тести спільної пам'яті відповідей (app/static/js/api_cache.js) у Node без браузера.
import { test } from "node:test";
import assert from "node:assert/strict";

const c = await import(new URL("../../app/static/js/api_cache.js", import.meta.url).href);

const fakeFetch = () => {
  const calls = [];
  const f = async (input) => { calls.push(String(input)); await new Promise((r) => setTimeout(r, 5)); return new Response(JSON.stringify({ n: calls.length }), { status: 200, headers: { "Content-Type": "application/json" } }); };
  f.calls = calls;
  return f;
};
const memStorage = () => { const m = new Map(); return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v), size: () => m.size }; };

test("ключ: розрахункові GET нормалізуються (порядок параметрів байдужий), решта — не кешується", () => {
  assert.equal(c.cacheKey("GET", "/api/timeline?lat=1&lon=2"), c.cacheKey("get", "/api/timeline?lon=2&lat=1"));
  assert.notEqual(c.cacheKey("GET", "/api/timeline?lat=1"), c.cacheKey("GET", "/api/timeline?lat=2"));
  assert.equal(c.cacheKey("POST", "/api/mission"), null);
  assert.equal(c.cacheKey("GET", "/api/data/status"), null);
  assert.equal(c.cacheKey("GET", "/assets/globe/x.png"), null);
  assert.ok(c.cacheKey("GET", "/api/sites/shackleton"));
  assert.ok(c.cacheKey("GET", "/api/launch-window?launch_site=kourou"));
});

test("однакові одночасні запити зливаються в один, готові беруться з пам'яті", async () => {
  const real = fakeFetch(), f = c.withCache(real);
  const [a, b, d] = await Promise.all([f("/api/timeline?lat=1"), f("/api/timeline?lat=1"), f("/api/timeline?lon=1&lat=1".replace("lon=1&", ""))]);
  assert.equal(real.calls.length, 1);
  assert.deepEqual(await a.json(), await b.json());
  assert.deepEqual(await d.json(), { n: 1 });
  await f("/api/timeline?lat=1");
  assert.equal(real.calls.length, 1);
  assert.equal(f.stats.network, 1);
  assert.ok(f.stats.shared >= 2 && f.stats.hits >= 1);
  await f("/api/timeline?lat=2");
  assert.equal(real.calls.length, 2);
});

test("між вкладками: відповідь із sessionStorage замість нового запиту; після TTL — знову в мережу", async () => {
  const storage = memStorage(); let t = 1000;
  const first = c.withCache(fakeFetch(), { storage, now: () => t });
  await first("/api/horizon?lat=1&lon=2");
  assert.equal(storage.size(), 1);
  const real2 = fakeFetch(), second = c.withCache(real2, { storage, now: () => t + 1000 });
  const res = await second("/api/horizon?lon=2&lat=1");
  assert.equal(real2.calls.length, 0);
  assert.deepEqual(await res.json(), { n: 1 });
  const real3 = fakeFetch(), late = c.withCache(real3, { storage, now: () => t + c.TTL_MS + 1 });
  await late("/api/horizon?lat=1&lon=2");
  assert.equal(real3.calls.length, 1);
});

test("помилки й POST не кешуються; скасування одного виклику не рве інші", async () => {
  let n = 0;
  const failing = async () => { n += 1; return new Response("{}", { status: 503 }); };
  const f = c.withCache(failing);
  await f("/api/metrics?lat=1"); await f("/api/metrics?lat=1");
  assert.equal(n, 2);
  const real = fakeFetch(), g = c.withCache(real);
  await g("/api/mission", { method: "POST", body: "{}" }); await g("/api/mission", { method: "POST", body: "{}" });
  assert.equal(real.calls.length, 2);
  const ctrl = new AbortController();
  const p1 = g("/api/system?x=1", { signal: ctrl.signal }), p2 = g("/api/system?x=1");
  ctrl.abort();
  await assert.rejects(p1, { name: "AbortError" });
  assert.deepEqual(await (await p2).json(), { n: 3 });
});

test("надто великі відповіді лишаються лише в пам'яті сторінки, не в sessionStorage", async () => {
  const storage = memStorage();
  const big = async () => new Response("x".repeat(c.MAX_STORED_BYTES + 10), { status: 200, headers: { "Content-Type": "text/plain" } });
  const f = c.withCache(big, { storage });
  await f("/api/terrain?lat=1");
  assert.equal(storage.size(), 0);
});
