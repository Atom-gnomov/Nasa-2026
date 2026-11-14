import assert from "node:assert/strict";
import { test } from "node:test";
import { expandedWidget, fitSideWidgets, normalizeWidgetStates, widgetTransition } from "../../app/static/js/workspace_state.js";

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

test("two normal panels fit on wide screens without automatic collapse", () => {
  const full = { left: "normal", right: "normal" };
  assert.deepEqual(fitSideWidgets(full, 1440, 340), full);
  assert.deepEqual(fitSideWidgets(full, 600, 275), full);
});

test("narrow view collapses opposite panel and restores it on resize", () => {
  const saved = { left: "normal", right: "normal" };
  assert.deepEqual(fitSideWidgets(saved, 560, 275, "left"), { left: "normal", right: "collapsed" });
  assert.deepEqual(fitSideWidgets(saved, 560, 275, "right"), { left: "collapsed", right: "normal" });
  assert.deepEqual(fitSideWidgets(saved, 1440, 340), saved);
  assert.deepEqual(saved, { left: "normal", right: "normal" }, "automatic fit does not change saved state");
});

test("expanded and manually collapsed widget states are respected on narrow screens", () => {
  assert.deepEqual(fitSideWidgets({ left: "expanded", right: "collapsed" }, 390, 275), { left: "expanded", right: "collapsed" });
  assert.deepEqual(fitSideWidgets({ left: "collapsed", right: "normal" }, 390, 275), { left: "collapsed", right: "normal" });
});
