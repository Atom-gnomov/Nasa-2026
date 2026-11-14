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
