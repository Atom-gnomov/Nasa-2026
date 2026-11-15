// Тести стану екрана завантаження (app/static/js/boot_loader.js) у Node без браузера.
import { test } from "node:test";
import assert from "node:assert/strict";

const { loaderState } = await import(new URL("../../app/static/js/boot_loader.js", import.meta.url).href);

const ds = (id, state, message = null) => ({ id, label: `Набір ${id}`, state, message });

test("набір готується — чекаємо, смуга показує готові набори й рядок скрипта", () => {
  const s = loaderState({ datasets: [ds("a", "ready"), ds("b", "running", "завантажую 40 %"), ds("c", "missing")] });
  assert.equal(s.kind, "wait");
  assert.ok(Math.abs(s.progress - 1 / 3) < 1e-9);
  assert.equal(s.text, "Набір b — завантажую 40 %");
});

test("автозапуск ще не стартував — коротко чекаємо, потім не тримаємо набір, який ніхто не готує", () => {
  const status = { auto_prepare: true, datasets: [ds("a", "ready"), ds("b", "missing")] };
  assert.equal(loaderState(status, 0).kind, "wait");
  assert.equal(loaderState(status, 10).kind, "ready");
  assert.equal(loaderState({ auto_prepare: false, datasets: [ds("b", "missing")] }, 0).kind, "ready");
});

test("збій підготовки — не відкриваємо мовчки, показуємо причину", () => {
  const s = loaderState({ datasets: [ds("a", "ready"), ds("b", "failed", "немає мережі")] });
  assert.equal(s.kind, "failed");
  assert.equal(s.text, "Набір b: немає мережі");
});

test("усе готове чи немає відповіді — готово", () => {
  assert.equal(loaderState({ datasets: [ds("a", "ready")] }).kind, "ready");
  assert.equal(loaderState({}).kind, "ready");
  assert.equal(loaderState(undefined).progress, 1);
});
