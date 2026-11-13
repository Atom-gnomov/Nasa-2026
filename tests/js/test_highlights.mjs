import assert from "node:assert/strict";
import { test } from "node:test";

import { getHighlights, publishHighlights, subscribeHighlights } from "../../app/static/js/highlights.js";

test("підписник одразу отримує поточний список і всі наступні", () => {
  publishHighlights([{ lat: -89, lon: 10, rank: 1, feasible: true }]);
  const seen = [];
  const off = subscribeHighlights((list) => seen.push(list.length));
  publishHighlights([{ lat: -80, lon: 0, rank: 1 }, { lat: -81, lon: 5, rank: 2 }]);
  assert.deepEqual(seen, [1, 2]);
  off();
  publishHighlights([]);
  assert.deepEqual(seen, [1, 2], "після відписки обробник мовчить");
});

test("некоректні точки відкидаються, список копіюється", () => {
  publishHighlights([{ lat: -80, lon: 0, rank: 1 }, { lat: "x", lon: 1 }, null, { lon: 3 }]);
  const list = getHighlights();
  assert.equal(list.length, 1);
  list.push({ lat: 1, lon: 1 });
  assert.equal(getHighlights().length, 1, "зовнішня зміна не псує стан");
  publishHighlights("не список");
  assert.deepEqual(getHighlights(), []);
});
