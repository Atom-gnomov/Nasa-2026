// Тести очікування екрана завантаження (app/static/js/boot_loader.js) у Node без браузера.
import { test } from "node:test";
import assert from "node:assert/strict";

const { dataReady } = await import(new URL("../../app/static/js/boot_loader.js", import.meta.url).href);

test("набір ще готується — чекаємо", () => {
  assert.equal(dataReady({ datasets: [{ id: "a", state: "ready" }, { id: "b", state: "running" }] }), false);
});

test("усе готове, відсутнє чи збійне — не чекаємо", () => {
  assert.equal(dataReady({ datasets: [{ id: "a", state: "ready" }, { id: "b", state: "missing" }, { id: "c", state: "failed" }] }), true);
  assert.equal(dataReady({}), true);
  assert.equal(dataReady(undefined), true);
});
