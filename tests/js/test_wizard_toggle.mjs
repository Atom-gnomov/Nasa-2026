// Тести кнопки «Місії» (app/static/js/wizard_toggle.js): початковий стан смуги кроків.
import { test } from "node:test";
import assert from "node:assert/strict";

const w = await import(new URL("../../app/static/js/wizard_toggle.js", import.meta.url).href);

test("збережений вибір важливіший за адресу", () => {
  assert.equal(w.wizardInitial("1", "/moon", ""), true);
  assert.equal(w.wizardInitial("0", "/report", "?step=10"), false);
});

test("без вибору: відкрита з кроку (?step=n) і на сторінках планування; на «Місяці» й «Системі» згорнута", () => {
  assert.equal(w.wizardInitial(null, "/mission", "?datetime=x&step=7"), true);
  assert.equal(w.wizardInitial(null, "/consistency", ""), true);
  assert.equal(w.wizardInitial(null, "/report", ""), true);
  for (const page of ["/mission", "/plan", "/search", "/consistency", "/report"]) assert.equal(w.wizardInitial(null, page, ""), true, page);
  assert.equal(w.wizardInitial(null, "/moon", ""), false);
  assert.equal(w.wizardInitial(null, "/system", ""), false);
  assert.equal(w.wizardInitial(null, "/system/earth-moon", ""), false);
  assert.equal(w.wizardInitial(null, "/moon", "?mystep=3"), false);
});
