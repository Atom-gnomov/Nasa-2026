// Тести вкладки «Вікно запуску» (app/static/js/launch_window.js) у Node без браузера.
// Запуск: node --test tests/js/test_launch_window.mjs (або pytest tests/test_state_js.py).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const lw = await import(new URL("../../app/static/js/launch_window.js", import.meta.url).href);
const example = JSON.parse(readFileSync(new URL("../../contracts/examples.json", import.meta.url), "utf8")).LaunchWindow;

test("запит: період від дати календаря, кінець включно, пріоритети через кому", () => {
  const url = lw.launchWindowUrl({ siteId: "kourou", lat: -89.67, lon: 129.78, datetime: "2027-07-01T12:30Z", days: 30,
                                   trajectory: "direct", priorities: ["fuel", "light"] });
  const q = new URLSearchParams(url.split("?")[1]);
  assert.equal(url.split("?")[0], "/api/launch-window");
  assert.equal(q.get("start"), "2027-07-01");
  assert.equal(q.get("end"), "2027-07-30");
  assert.equal(q.get("priorities"), "fuel,light");
  assert.equal(q.get("launch_site"), "kourou");
});

test("запит: без точки чи майданчика — null; період обмежено 1…60 діб", () => {
  assert.equal(lw.launchWindowUrl({ siteId: "kourou", lat: null, lon: 0, datetime: "2027-07-01T00:00Z" }), null);
  assert.equal(lw.launchWindowUrl({ siteId: "", lat: 0, lon: 0, datetime: "2027-07-01T00:00Z" }), null);
  const long = new URLSearchParams(lw.launchWindowUrl({ siteId: "k", lat: 0, lon: 0, datetime: "2027-12-15T00:00Z", days: 500 }).split("?")[1]);
  assert.equal(long.get("end"), "2028-02-12"); // 60 діб через перехід року
});

test("addDays і movePriority", () => {
  assert.equal(lw.addDays("2028-02-28", 1), "2028-02-29");
  assert.deepEqual(lw.movePriority(["a", "b", "c"], 2, -1), ["a", "c", "b"]);
  assert.deepEqual(lw.movePriority(["a", "b", "c"], 0, -1), ["a", "b", "c"]);
});

test("шкала з прикладу контракту: одна найкраща дата, відсотки в межах 0…100", () => {
  const items = lw.scaleItems(example);
  assert.equal(items.length, example.days.length);
  assert.equal(items.filter((i) => i.best).length, 1);
  assert.equal(items.find((i) => i.best).date, example.best.date);
  for (const i of items) {
    assert.ok(i.pct >= 0 && i.pct <= 100);
    assert.ok(!i.title.includes("undefined") && !i.title.includes("NaN"), i.title);
  }
});

test("таблиця й підсумок без undefined/NaN", () => {
  const rows = lw.tableRows(example);
  assert.equal(rows.length, example.days.length);
  for (const r of rows) for (const c of r.cells) assert.ok(c && !/undefined|NaN/.test(c), c);
  const text = lw.bestText(example, "Куру");
  assert.match(text, new RegExp(example.best.date));
  assert.ok(!/undefined|NaN/.test(text));
  assert.equal(lw.calendarDatetime("2027-07-22"), "2027-07-22T00:00Z");
});
