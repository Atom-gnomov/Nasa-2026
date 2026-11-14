// Тести тексту банера «Готую дані» (app/static/js/data_status.js) у Node без браузера.
import { test } from "node:test";
import assert from "node:assert/strict";

const { bannerState } = await import(new URL("../../app/static/js/data_status.js", import.meta.url).href);

const ds = (id, state, message = null) => ({ id, label: `Набір ${id}`, state, message });

test("усе готове або не запущене — банера немає", () => {
  assert.deepEqual(bannerState({ datasets: [ds("a", "ready"), ds("b", "missing")] }), { kind: "hidden", text: "" });
  assert.equal(bannerState(undefined).kind, "hidden");
  assert.equal(bannerState({}).kind, "hidden");
});

test("під час підготовки — назви наборів і останній рядок скрипта", () => {
  const s = bannerState({ datasets: [ds("a", "running", "завантаження 3"), ds("b", "ready")] });
  assert.equal(s.kind, "running");
  assert.match(s.text, /Набір a/);
  assert.match(s.text, /завантаження 3/);
  assert.doesNotMatch(s.text, /Набір b/);
});

test("помилка — причина й можливість повторити; підготовка важливіша за помилку", () => {
  const failed = bannerState({ datasets: [ds("a", "failed", "немає мережі")] });
  assert.equal(failed.kind, "failed");
  assert.match(failed.text, /немає мережі/);
  assert.equal(bannerState({ datasets: [ds("a", "failed", "x"), ds("b", "running")] }).kind, "running");
});
