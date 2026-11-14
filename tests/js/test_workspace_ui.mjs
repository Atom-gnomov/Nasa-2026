import assert from "node:assert/strict";
import { test } from "node:test";
import { expandedWidget, normalizeWidgetStates, widgetTransition } from "../../app/static/js/workspace_state.js";

test("згортання і повернення не зачіпають другу панель", () => {
  const a = widgetTransition({left:"normal",right:"normal"},"left","collapse");
  assert.deepEqual(a, {left:"collapsed",right:"normal"});
  assert.deepEqual(widgetTransition(a,"left","collapse"), {left:"normal",right:"normal"});
});

test("розгортання займає половину сцени та згортає протилежний віджет", () => {
  const a = widgetTransition({left:"normal",right:"normal"},"left","expand");
  assert.deepEqual(a, {left:"expanded",right:"collapsed"});
  assert.equal(expandedWidget(a), "left");
  const b = widgetTransition(a,"right","expand");
  assert.deepEqual(b, {left:"collapsed",right:"expanded"});
  assert.equal(expandedWidget(b), "right");
});

test("повторне натискання розгортання повертає звичайну ширину", () => {
  const a = widgetTransition({left:"expanded",right:"collapsed"},"left","expand");
  assert.deepEqual(a, {left:"normal",right:"collapsed"});
  assert.equal(expandedWidget(a), "");
});

test("невалідний стан і некоректні дії не дають двох expanded", () => {
  assert.deepEqual(normalizeWidgetStates({left:"expanded",right:"expanded"}), {left:"expanded",right:"collapsed"});
  assert.deepEqual(widgetTransition({left:"wrong"},"left","bad"), {left:"normal",right:"normal"});
  assert.deepEqual(widgetTransition({left:"normal"},"right","expand",["left"]), {left:"normal"});
});
