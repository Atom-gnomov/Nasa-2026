// Чисті правила станів віджетів: не залежать від браузера, придатні для node:test.
const MODES = new Set(["normal", "collapsed", "expanded"]);
export const SIDES = ["left", "right"];

export function normalizeWidgetStates(raw = {}, present = SIDES) {
  const result = {};
  for (const side of present) result[side] = MODES.has(raw?.[side]) ? raw[side] : "normal";
  // Після відновлення sessionStorage одночасно розгорнутими панелі бути не можуть.
  if (result.left === "expanded" && result.right === "expanded") result.right = "collapsed";
  if (result.left === "expanded" && "right" in result) result.right = "collapsed";
  if (result.right === "expanded" && "left" in result) result.left = "collapsed";
  return result;
}

// Телефон (≤ 760px): на сторінках зі сценою перший вхід — обидві панелі згорнуті, щоб глобус був видний;
// панель відкривається однією кнопкою (›/‹) і лишається збереженою на сесію. Є збережений стан — не чіпаємо.
export const PHONE_MAX_WIDTH = 760;
export function phoneDefaultStates(saved, present, viewportWidth, hasScene) {
  const empty = !saved || Object.keys(saved).length === 0;
  if (!hasScene || !empty || !(Number(viewportWidth) <= PHONE_MAX_WIDTH)) return saved;
  return Object.fromEntries(present.map((side) => [side, "collapsed"]));
}

export function widgetTransition(raw, side, action, present = SIDES) {
  const next = normalizeWidgetStates(raw, present);
  if (!present.includes(side) || !["collapse", "expand"].includes(action)) return next;
  const current = next[side];
  if (action === "collapse") next[side] = current === "collapsed" ? "normal" : "collapsed";
  if (action === "expand") {
    next[side] = current === "expanded" ? "normal" : "expanded";
    if (next[side] === "expanded") {
      const opposite = side === "left" ? "right" : "left";
      if (opposite in next) next[opposite] = "collapsed";
    }
  }
  return next;
}

export const expandedWidget = (states) => SIDES.find((side) => states?.[side] === "expanded") ?? "";

/**
 * Keep both panels open whenever they fit. When the viewport becomes too
 * narrow, collapse only the opposite panel in the *rendered* state; the
 * caller's saved preference is not mutated and returns on wider screens.
 */
export function fitSideWidgets(raw, viewportWidth, panelWidth, preferredSide = "left", gap = 50) {
  const next = normalizeWidgetStates(raw);
  const width = Number(viewportWidth), panel = Number(panelWidth);
  if (!Number.isFinite(width) || !Number.isFinite(panel) || width >= panel * 2 + gap ||
      expandedWidget(next) || next.left === "collapsed" || next.right === "collapsed") return next;
  next[preferredSide === "right" ? "left" : "right"] = "collapsed";
  return next;
}


/**
 * Reserve the actual widths of currently visible fixed widgets, keeping the
 * camera centered in the remaining open stage. Insets are measured from the
 * viewport edges and include the space between widgets and the render host.
 * On narrow screens we deliberately fall back to a full-screen scene behind
 * collapsible panels rather than rendering a useless 10px-wide canvas.
 */
export function sceneInsets(viewportWidth, leftInset, rightInset, expanded = "none", minStageWidth = 210) {
  const width = Math.max(0, Number(viewportWidth) || 0);
  if (width <= 0) return { left: 0, right: 0, compact: true };
  const positive = (n) => Math.max(0, Math.min(width, Number(n) || 0));
  const half = width / 2;
  const left = expanded === "left" ? half : positive(leftInset);
  const right = expanded === "right" ? half : positive(rightInset);
  if (width - left - right < minStageWidth) return { left: 0, right: 0, compact: true };
  return { left, right, compact: false };
}
