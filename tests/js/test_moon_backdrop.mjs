// Тести вибору сторінок для Місяця-тла (app/static/js/moon_backdrop.js) у Node без браузера.
import { test } from "node:test";
import assert from "node:assert/strict";

const { wantsBackdrop } = await import(new URL("../../app/static/js/moon_backdrop.js", import.meta.url).href);

test("Місяць-тло — на сторінках кроків планування", () => {
  for (const p of ["mission", "search", "plan", "consistency", "report"]) assert.equal(wantsBackdrop(`page-${p} has-starfield`), true, p);
});

test("на «Місяці» і «Системі» власні 3D-сцени, тла немає", () => {
  assert.equal(wantsBackdrop("page-moon"), false);
  assert.equal(wantsBackdrop("page-system"), false);
  assert.equal(wantsBackdrop(""), false);
  assert.equal(wantsBackdrop(undefined), false);
});
