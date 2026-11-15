// Тести кроку 10 «Підсумковий звіт» (app/static/js/report.js) у Node без браузера.
import { test } from "node:test";
import assert from "node:assert/strict";

const r = await import(new URL("../../app/static/js/report.js", import.meta.url).href);

const state = { datetime: "2027-08-24T02:01Z", lat: -89.5, lon: 0, site: "shackleton" };

test("запит звіту: як для перевірки, плюс назва місця лише коли точку вибрано", () => {
  const body = r.buildReportRequest({ state, plan: { name: "Південь", goal: "ice" }, siteName: "Шеклтон" });
  assert.deepEqual(body.site, { lat: -89.5, lon: 0, name: "Шеклтон" });
  assert.equal(body.goal, "ice");
  const none = r.buildReportRequest({ state: { datetime: state.datetime }, siteName: "Шеклтон" });
  assert.equal(none.site, null);
  const unnamed = r.buildReportRequest({ state });
  assert.deepEqual(unnamed.site, { lat: -89.5, lon: 0 });
});

test("ім'я файлу з назви місії", () => {
  assert.equal(r.fileName("Південь-1", "md"), "південь-1.md");
  assert.equal(r.fileName("  «Шеклтон» 2027! ", "json"), "шеклтон-2027.json");
  assert.equal(r.fileName("", "md"), "mission.md");
  assert.equal(r.fileName(undefined, "md"), "mission.md");
});

test("завантаження: Markdown за замовчуванням, JSON — повний звіт", () => {
  const rep = { name: "Південь", markdown: "# Місія: Південь\n", sections: [] };
  const md = r.downloadParts(rep, "md");
  assert.deepEqual([md.name, md.text], ["південь.md", "# Місія: Південь\n"]);
  assert.match(md.type, /markdown/);
  const js = r.downloadParts(rep, "json");
  assert.equal(js.name, "південь.json");
  assert.deepEqual(JSON.parse(js.text), rep);
});

test("посилання назад на кроки: усі десять доступні й зберігають параметри адреси", () => {
  for (let n = 1; n <= 10; n += 1) assert.ok(r.stepLink(n, "?datetime=2027-08-24T02:01Z"), `крок ${n}`);
  assert.match(r.stepLink(9, "?datetime=x"), /^\/consistency\?.*step=9/);
  assert.match(r.stepLink(10), /^\/report\?step=10/);
  assert.equal(r.stepLink(11), null);
});

test("висновок звіту залежить від ok", () => {
  assert.match(r.verdictText({ ok: true }), /немає/);
  assert.match(r.verdictText({ ok: false }), /Є конфлікти/);
});
