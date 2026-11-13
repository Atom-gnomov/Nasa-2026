import assert from "node:assert/strict";
import { test } from "node:test";

import {
  DEFAULT_FORM, REGIONS, activePriorities, buildAdviceFacts, buildSearchRequest, highlightPoints, clampHours, describeComparison, gridNote, hoursShort,
  hoursText, maxHours, movePriority, placeLabel, resultRows, violationText,
} from "../../app/static/js/search.js";

const DATE = "2027-07-01T00:00Z";
const form = (patch = {}) => ({ ...structuredClone(DEFAULT_FORM), ...patch });

test("тіло запиту: період, область, пріоритети тільки ввімкнені", () => {
  const body = buildSearchRequest(form(), DATE);
  assert.equal(body.start, "2027-07-01T00:00:00Z");
  assert.equal(body.end, "2027-07-31T00:00:00Z");
  assert.deepEqual(body.region, { lat_min: -90, lat_max: -80 });
  assert.equal(body.grid_step_deg, 2);
  assert.deepEqual(body.priorities, ["energy", "comms"]);
  assert.equal(body.mode, "weighted");
  assert.equal(body.include_catalog, true);
});

test("нульові повзунки не надсилаються, ненульові — так", () => {
  const none = buildSearchRequest(form(), DATE);
  assert.ok(!("min_sun_hours" in none) && !("min_comm_hours" in none));
  const set = buildSearchRequest(form({ minSunHours: 200, minCommHours: 100 }), DATE);
  assert.equal(set.min_sun_hours, 200);
  assert.equal(set.min_comm_hours, 100);
});

test("власна область бере широти й крок із форми", () => {
  const body = buildSearchRequest(form({ regionKey: "custom", custom: { lat_min: -75, lat_max: -60, grid_step_deg: 3 } }), DATE);
  assert.deepEqual(body.region, { lat_min: -75, lat_max: -60 });
  assert.equal(body.grid_step_deg, 3);
});

test("готові області не змінюються спільним посиланням", () => {
  const body = buildSearchRequest(form({ regionKey: "whole" }), DATE);
  body.region.lat_min = 0;
  assert.equal(REGIONS.whole.region.lat_min, -90);
});

test("помилки: немає факторів, некоректна дата", () => {
  const off = form({ priorities: DEFAULT_FORM.priorities.map((p) => ({ ...p, on: false })) });
  assert.throws(() => buildSearchRequest(off, DATE), /щонайменше один фактор/);
  assert.throws(() => buildSearchRequest(form(), "не дата"), /дата/);
});

test("порядок пріоритетів: переставляння й межі", () => {
  const items = ["a", "b", "c"].map((id) => ({ id, on: true }));
  assert.deepEqual(movePriority(items, 2, 0).map((p) => p.id), ["c", "a", "b"]);
  assert.deepEqual(movePriority(items, 0, 1).map((p) => p.id), ["b", "a", "c"]);
  assert.equal(movePriority(items, 0, 0), items);
  assert.equal(movePriority(items, 0, -1), items);
  assert.equal(movePriority(items, 0, 3), items);
  assert.deepEqual(items.map((p) => p.id), ["a", "b", "c"], "вхідний масив не змінюється");
  const reordered = [{ id: "comms", on: true }, { id: "energy", on: false }, { id: "radiation", on: true }];
  assert.deepEqual(activePriorities(reordered), ["comms", "radiation"]);
});

test("повзунки: максимум = період у годинах, значення стискаються при скороченні періоду", () => {
  assert.equal(maxHours(30), 720);
  const f = clampHours(form({ days: 10, minSunHours: 600, minCommHours: 100 }));
  assert.equal(f.minSunHours, 240);
  assert.equal(f.minCommHours, 100);
});

test("підписи: години, місце, порушення", () => {
  assert.equal(hoursText(12.34), "12.3 год");
  assert.equal(hoursText(72), "72 год (3 доби)");
  assert.equal(hoursShort(343.4), "343 год");
  assert.equal(placeLabel({ name: "Шеклтон", lat: -89.7, lon: 129.8 }), "Шеклтон");
  assert.equal(placeLabel({ name: null, lat: -87.5, lon: 12.345 }), "87.50° пд. ш., 12.35° сх. д.");
  assert.equal(placeLabel({ name: null, lat: 10, lon: -20 }), "10.00° пн. ш., 20.00° зх. д.");
  assert.match(violationText({ requirement: "min_sun_hours", value: 100, required: 300 }), /Сонця: 100 год \(4\.2 доби\) із потрібних 300 год \(12\.5 доби\)/);
});

const cmp = (dominance, factors, extra = {}) => ({
  dominance, decisive_factor: null, score_delta_pct: 5, per_factor: factors, ...extra,
});

test("порівняння простою мовою для всіх чотирьох випадків", () => {
  const a = cmp("a", [{ factor: "energy", winner: "a" }, { factor: "comms", winner: "tie" }]);
  assert.match(describeComparison(a), /не гірша за другу.*енергія.*\+5\.0/);
  const b = cmp("b", [{ factor: "comms", winner: "b" }]);
  assert.match(describeComparison(b), /Друга точка.*зв'язок.*порядок пріоритетів/);
  assert.match(describeComparison(cmp("tie", [])), /практично однакові/);
  const t = cmp("tradeoff", [{ factor: "energy", winner: "a" }, { factor: "comms", winner: "b" }], { decisive_factor: "energy" });
  const text = describeComparison(t);
  assert.match(text, /Компроміс.*виграє за енергія.*програє за зв'язок/);
  assert.match(text, /Вирішальний фактор — енергія/);
  assert.equal(describeComparison(null), "");
});

test("примітка про сітку попереджає при обрізанні за бюджетом часу", () => {
  const ok = gridNote({ evaluated: 95, candidates: 95, step_deg: 2, truncated: false });
  assert.match(ok, /95 з 95/);
  assert.ok(!/Бюджет/.test(ok));
  assert.match(gridNote({ evaluated: 40, candidates: 95, step_deg: 2, truncated: true }), /Бюджет часу.*зменште область/);
});

test("рядки результатів зі зразка відповіді", () => {
  const response = {
    priorities: ["energy", "comms"],
    chains: [{
      rank: 1, moon_site: { site_id: null, name: null, lat: -90, lon: 0 }, dsn_station_id: "madrid", dsn_hours: 144,
      launch_site_id: null, earth_target: null, feasible: true, violations: [], score_pct: 71.55, pareto: true,
      factors: { energy: 0.9996, comms: 0.37 }, summary: { sun_hours: 239.9, comm_hours: 106 }, horizon_source: "flat",
    }, {
      rank: 2, moon_site: { site_id: "apollo-11", name: "Apollo 11", lat: 0.67, lon: 23.47 }, dsn_station_id: null, dsn_hours: 0,
      launch_site_id: null, earth_target: null, feasible: false,
      violations: [{ requirement: "min_sun_hours", value: 100, required: 300 }], score_pct: 40, pareto: false,
      factors: { energy: 0.3, comms: 0.9 }, summary: { sun_hours: 100, comm_hours: 240 }, horizon_source: "flat",
    }],
  };
  const [first, second] = resultRows(response);
  assert.equal(first.place, "90.00° пд. ш., 0.00° сх. д.");
  assert.equal(first.station, "madrid · 144 год");
  assert.equal(first.sun, "240 год");
  assert.equal(first.comm, "106 год");
  assert.deepEqual(first.factors.map((f) => f.label), ["Енергія", "Зв'язок"]);
  assert.equal(first.pareto, true);
  assert.equal(second.station, "—");
  assert.equal(second.feasible, false);
  assert.match(second.violations[0], /Сонця/);
});

test("факти для порад: лише топ-5, готові числа відповіді, без undefined", () => {
  const chain = (rank) => ({
    rank, moon_site: { site_id: null, name: null, lat: -88 + rank, lon: 10 }, dsn_station_id: "madrid", dsn_hours: 100,
    launch_site_id: null, earth_target: null, feasible: rank !== 3,
    violations: rank === 3 ? [{ requirement: "min_sun_hours", value: 5, required: 300 }] : [],
    score_pct: 80 - rank, pareto: false, factors: { energy: 0.5, comms: 0.4 },
    summary: { sun_hours: 200, comm_hours: 150 }, horizon_source: "flat",
  });
  const response = {
    period: { start: "2027-07-01T00:00:00Z", end: "2027-07-31T00:00:00Z", period_h: 720, step_h: 6 },
    mode: "weighted", priorities: ["energy", "comms"], weights: { energy: 0.75, comms: 0.25 },
    grid: { evaluated: 95, candidates: 95, truncated: false, step_deg: 2 },
    chains: [1, 2, 3, 4, 5, 6, 7].map(chain),
    comparison: { dominance: "tradeoff", decisive_factor: "energy", score_delta_pct: 3, per_factor: [], a_rank: 1, b_rank: 2 },
  };
  const facts = buildAdviceFacts(response, { ...DEFAULT_FORM, minSunHours: 300 });
  assert.equal(facts.top.length, 5);
  assert.equal(facts.top[2].feasible, false);
  assert.equal(facts.requirements.min_sun_hours, 300);
  assert.equal(facts.requirements.min_comm_hours, null);
  assert.equal(facts.candidates.total, 95);
  assert.deepEqual(facts.comparison.dominance, "tradeoff");
  assert.ok(!JSON.stringify(facts).includes("undefined"));
  assert.ok(JSON.stringify(facts).length < 12000);
  assert.equal(buildAdviceFacts({ ...response, comparison: null }, DEFAULT_FORM).comparison, null);
});

test("точки для карти: координати, ранг, допустимість", () => {
  const response = { chains: [
    { rank: 1, feasible: true, moon_site: { lat: -89.5, lon: 10 } },
    { rank: 2, feasible: false, moon_site: { lat: -80, lon: -170.25 } },
  ] };
  assert.deepEqual(highlightPoints(response), [
    { lat: -89.5, lon: 10, rank: 1, feasible: true },
    { lat: -80, lon: -170.25, rank: 2, feasible: false },
  ]);
});

