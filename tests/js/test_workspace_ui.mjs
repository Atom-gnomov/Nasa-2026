import assert from "node:assert/strict";
import { test } from "node:test";
import { expandedWidget, fitSideWidgets, normalizeWidgetStates, sceneInsets, widgetTransition } from "../../app/static/js/workspace_state.js";

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

test("320px phones reserve space for a collapsed 43px edge control", () => {
  const viewport = 320;
  const panel = Math.min(275, viewport - 92);
  const drawn = fitSideWidgets({left:"normal", right:"normal"}, viewport, panel, "left");
  assert.equal(drawn.right, "collapsed");
  // Left margin 13; right pill width 43 and right margin 13; >=20px gap.
  assert.ok(viewport - 13 - 43 - (13 + panel) >= 20);
});

test("scene center follows free area between visible panels", () => {
  assert.deepEqual(sceneInsets(1440, 362, 362), { left: 362, right: 362, compact: false });
  assert.deepEqual(sceneInsets(1440, 362, 66), { left: 362, right: 66, compact: false });
  const shifted = sceneInsets(1440, 362, 66);
  assert.equal((shifted.left + (1440 - shifted.right)) / 2, 868);
});
test("expanded scene still honors the half-screen boundary", () => {
  assert.deepEqual(sceneInsets(1440, 362, 66, "left"), { left: 720, right: 66, compact: false });
  assert.deepEqual(sceneInsets(1440, 66, 362, "right"), { left: 66, right: 720, compact: false });
});
test("mobile fallback never creates an unusably thin 3D canvas", () => {
  assert.deepEqual(sceneInsets(390, 290, 66), { left: 0, right: 0, compact: true });
  assert.deepEqual(sceneInsets(0, 0, 0), { left: 0, right: 0, compact: true });
});
