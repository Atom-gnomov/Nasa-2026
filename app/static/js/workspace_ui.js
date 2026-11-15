// Спільна оболонка робочого простору. DOM/ID існуючих модулів НЕ замінюємо:
// переміщуємо наявні вузли до фіксованих віджетів, зберігаючи обробники та canvas.
import { expandedWidget, fitSideWidgets, normalizeWidgetStates, sceneInsets, widgetTransition } from "./workspace_state.js";

const page = document.body.className.match(/page-(moon|system|search|mission|launch|plan)/)?.[1];
const widgets = {};
const root = document.body;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function prepareWidget(target, side, name, { scene = false } = {}) {
  if (!target) return;
  target.classList.add("ui-widget", "ui-widget-" + side);
  if (scene) target.classList.add("ui-scene-widget");
  const body = element("div", "widget-body");
  body.id = "widget-content-" + page + "-" + side;
  while (target.firstChild) body.append(target.firstChild);
  const header = element("div", "widget-header");
  const title = element("strong", "widget-title", name);
  const actions = element("div", "widget-actions");
  const collapse = element("button", "widget-action widget-collapse", "−");
  collapse.type = "button";
  collapse.dataset.widgetAction = "collapse";
  collapse.title = "Згорнути панель";
  collapse.setAttribute("aria-label", "Згорнути панель");
  collapse.setAttribute("aria-controls", body.id);
  const expand = element("button", "widget-action widget-expand", "⤢");
  expand.type = "button";
  expand.dataset.widgetAction = "expand";
  expand.title = "Розгорнути панель на пів екрана";
  expand.setAttribute("aria-label", "Розгорнути панель на пів екрана");
  expand.setAttribute("aria-controls", body.id);
  actions.append(collapse); // розширення панелей прибрано: лише згортання
  header.append(title, actions);
  target.append(header, body);
  widgets[side] = { target, collapse, expand };
  collapse.addEventListener("click", () => updateState(side, "collapse"));
  return body;
}

function createDock(name, items, owner = root) {
  const dock = element("section", "ui-dock");
  dock.setAttribute("aria-label", name);
  const heading = element("div", "dock-header");
  const title = element("span", "dock-title", name);
  const toggle = element("button", "dock-toggle", "⌄");
  toggle.type = "button";
  toggle.title = "Згорнути налаштування";
  toggle.setAttribute("aria-label", "Згорнути налаштування");
  toggle.setAttribute("aria-expanded", "true");
  const content = element("div", "dock-content");
  content.id = "dock-content-" + page + "-" + document.querySelectorAll(".ui-dock").length;
  toggle.setAttribute("aria-controls", content.id);
  for (const item of items) if (item) content.append(item);
  const storageKey = "lse-ui-dock:" + page + ":" + name;
  const applyDockState = (collapsed) => {
    dock.classList.toggle("is-collapsed", collapsed);
    const open = !collapsed;
    toggle.textContent = open ? "⌄" : "⌃";
    toggle.title = open ? "Згорнути налаштування" : "Розгорнути налаштування";
    toggle.setAttribute("aria-label", toggle.title);
    toggle.setAttribute("aria-expanded", String(open));
  };
  try { applyDockState(sessionStorage.getItem(storageKey) === "collapsed"); }
  catch { applyDockState(false); }
  toggle.addEventListener("click", () => {
    const collapsed = !dock.classList.contains("is-collapsed");
    applyDockState(collapsed);
    try { sessionStorage.setItem(storageKey, collapsed ? "collapsed" : "open"); } catch { /* приватний режим */ }
  });
  heading.append(title, toggle);
  dock.append(heading, content);
  owner.append(dock);
  return { dock, heading, content };
}



/**
 * Compact dock: all native controls are MOVED (never cloned) into small pages.
 * This replaces horizontal/vertical sliders with explicit functional tabs.
 * Read-only sources can expand, without making the default dock tall.
 */
function tabifyDock(dockParts, groups, key) {
  const { dock, heading, content } = dockParts;
  dock.classList.add("ui-tabbed-dock");
  const tabs = element("div", "dock-tabs");
  tabs.setAttribute("role", "tablist");
  tabs.setAttribute("aria-label", "Групи налаштувань");
  const panels = element("div", "dock-pages");
  const records = [];
  for (const [i, group] of groups.entries()) {
    const button = element("button", "dock-tab" + (i === 0 ? " active" : ""), group.label);
    button.type = "button";
    button.id = "dock-tab-" + key + "-" + i;
    const panel = element("div", "dock-page");
    panel.id = "dock-page-" + key + "-" + i;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-controls", panel.id);
    panel.setAttribute("role", "tabpanel");
    panel.setAttribute("aria-labelledby", button.id);
    for (const node of group.nodes) if (node) panel.append(node);
    tabs.append(button);
    panels.append(panel);
    records.push({ button, panel });
  }
  function select(index) {
    records.forEach(({ button, panel }, i) => {
      const selected = i === index;
      button.classList.toggle("active", selected);
      button.setAttribute("aria-selected", String(selected));
      button.tabIndex = selected ? 0 : -1;
      panel.hidden = !selected;
    });
    dock.dataset.activeGroup = String(index);
    requestAnimationFrame(() => {
      refreshSceneBounds();
      window.dispatchEvent(new Event("resize"));
    });
  }
  records.forEach(({button}, i) => {
    button.addEventListener("click", () => select(i));
    button.addEventListener("keydown", (e) => {
      const next = e.key === "ArrowRight" ? (i + 1) % records.length
        : e.key === "ArrowLeft" ? (i - 1 + records.length) % records.length : -1;
      if (next < 0) return;
      e.preventDefault();
      records[next].button.focus();
      select(next);
    });
  });
  content.replaceChildren(panels);
  const headingTitle = heading.querySelector(".dock-title");
  heading.insertBefore(tabs, headingTitle);
  select(0);
  return dockParts;
}

function moonDockGroups(parts) {
  const first = parts.content.querySelector(".globe-toolbar:not(.layer-toolbar)");
  const layer = parts.content.querySelector(".globe-toolbar.layer-toolbar");
  const legend = parts.content.querySelector("#layer-legend");
  const sources = parts.content.querySelector(".globe-sources");
  const wrapped = (id) => document.getElementById(id)?.closest("label");
  const groups = [
    {label:"Вигляд", nodes:[first?.querySelector('[data-view="globe"]')?.closest(".seg"), wrapped("light-mode"), wrapped("quality-select")]},
    {label:"Сітка й рельєф", nodes:[wrapped("grid-toggle"),wrapped("grid-step"),wrapped("relief"),wrapped("contour-toggle"),wrapped("contour-step")]},
    {label:"Шари", nodes:[layer?.querySelector('[data-layer="color"]')?.closest(".seg"), wrapped("temp-kind")]},
    {label:"Шкала", nodes:[legend]},
    {label:"Джерела", nodes:[sources]},
  ];
  tabifyDock(parts,groups,"moon");
}

function systemDockGroups(parts) {
  const toolbar = parts.content.querySelector(".system-toolbar");
  const wrapped = (id) => document.getElementById(id)?.closest("label");
  const mode = toolbar?.querySelector(".mode-switch");
  const time = document.getElementById("system-play")?.closest(".time-controls");
  const simulation = document.getElementById("system-sim-controls");
  tabifyDock(parts,[
    {label:"Система",nodes:[mode,wrapped("system-scale"),wrapped("quality-select")]},
    {label:"Час",nodes:[time]},
    {label:"Політ",nodes:[wrapped("system-path"),simulation]},
    {label:"Дані",nodes:[parts.content.querySelector("#system-note"),parts.content.querySelector(".globe-sources")]},
  ],"system");
}

function initMoon() {
  const left = document.querySelector(".moon-layout > .side-panel");
  const right = document.getElementById("metrics-overlay");
  prepareWidget(left, "left", "Вибір місця та графіки", { scene: true });
  prepareWidget(right, "right", "Метрики", { scene: true });
  const globe = document.querySelector(".globe-wrap");
  if (!globe) return;
  const controls = [...globe.querySelectorAll(":scope > .globe-toolbar, :scope > #layer-legend, :scope > .globe-sources")];
  const mainDock = createDock("Налаштування карти", controls);
  const { heading } = mainDock;
  moonDockGroups(mainDock);
  const modes = element("div", "scene-mode-switch seg");
  for (const [mode, name] of [["globe", "Глобус"], ["surface", "Вид з поверхні"]]) {
    const button = element("button", mode === "globe" ? "active" : "", name);
    button.type = "button";
    button.dataset.sceneMode = mode;
    button.setAttribute("aria-pressed", String(mode === "globe"));
    button.addEventListener("click", () => {
      window.dispatchEvent(new CustomEvent("scene-mode", { detail: { mode } })); // глобус на льоту наближається/віддаляється
      root.classList.toggle("surface-active", mode === "surface");
      for (const b of modes.querySelectorAll("button")) {
        const active = b.dataset.sceneMode === mode;
        b.classList.toggle("active", active);
        b.setAttribute("aria-pressed", String(active));
      }
      requestAnimationFrame(() => {
        updateSceneClearance();
        window.dispatchEvent(new Event("resize"));
      });
    });
    modes.append(button);
  }
  heading.prepend(modes);
  // Док глобуса ховається у виді з поверхні: потрібна окрема видима
  // кнопка повернення, інакше користувач залишиться в цьому режимі.
  const surface = document.getElementById("surface");
  if (surface) {
    const surfaceTools = [...surface.querySelectorAll(":scope > .surface-toolbar")];
    const surfaceDock = createDock("Налаштування огляду", surfaceTools, surface);
    surfaceDock.dock.classList.add("ui-surface-dock");
    // Keep all original handlers/IDs; group the 3 rows into 3 compact tabs.
    tabifyDock(surfaceDock,[
      {label:"Огляд",nodes:[...surfaceTools[0]?.children ?? []]},
      {label:"Час",nodes:[...surfaceTools[1]?.children ?? []]},
      {label:"Рельєф",nodes:[...surfaceTools[2]?.children ?? []]},
    ],"surface");
    const back = element("button", "surface-back", "← Глобус");
    back.type = "button";
    back.title = "Повернутися до глобуса";
    back.setAttribute("aria-label", "Повернутися до глобуса");
    back.addEventListener("click", () => modes.querySelector('[data-scene-mode="globe"]').click());
    surfaceDock.heading.prepend(back);
  }
}

function initSystem() {
  const layout = document.querySelector(".system-layout");
  if (!layout) return;
  const toolbar = layout.querySelector(".system-toolbar");
  const left = element("aside", "side-panel system-pick");
  layout.prepend(left);
  const focus = toolbar?.querySelector('[aria-label="Центр огляду"]');
  const flight = toolbar?.querySelector("#system-flight")?.closest("label");
  if (focus) left.append(focus);
  if (flight) left.append(flight);
  const point = element("p", "muted small", "Оберіть об'єкт або параметри польоту. Місце посадки можна вибрати на Місяці.");
  left.append(point);
  // Пере-використовуємо наявний графік /api/timeline для вибраної точки.
  // Цей canvas створюється до завантаження charts.js з system.html.
  const graph = element("section", "system-graph");
  graph.append(element("h3", "", "Сонце, Земля й зв'язок за місячну добу"));
  const chart = element("canvas", "timeline-chart");
  chart.id = "timeline-chart";
  chart.setAttribute("aria-label", "Кут Сонця й Землі над горизонтом і вікна зв'язку DSN за місячну добу");
  const summary = element("p", "muted small", "Виберіть місце на Місяці");
  summary.id = "timeline-summary";
  const readout = element("p", "muted small");
  readout.id = "timeline-readout";
  graph.append(chart, summary, readout);
  left.append(graph);
  prepareWidget(left, "left", "Вибір об'єкта та польоту", { scene: true });
  const right = layout.querySelector(".system-info");
  const rightBody = prepareWidget(right, "right", "Метрики системи", { scene: true });
  const metrics = document.getElementById("metrics-overlay");
  if (rightBody && metrics) {
    const details = element("details", "system-point-metrics");
    details.append(element("summary", "", "Метрики точки посадки"), metrics);
    rightBody.append(details);
    metrics.classList.add("ui-embedded-metrics");
  }
  const mainDock = createDock("Налаштування системи", [toolbar, layout.querySelector("#system-note"), layout.querySelector(".globe-sources")]);
  systemDockGroups(mainDock);
}

function initSearch() {
  const root = document.getElementById("search");
  if (!root) return;
  const advice = root.querySelector("#s-advice");
  if (advice) root.append(advice); // третя колонка, окремий віджет ШІ
  prepareWidget(root.querySelector(".search-form"), "left", "Вимоги та пріоритети");
  prepareWidget(advice, "right", "Поради ШІ");
}

function initAnalytics() {
  const layout = document.querySelector(".mission-layout, .lw-layout");
  if (!layout) return;
  prepareWidget(layout.querySelector(".mission-form, .lw-controls"), "left", "Налаштування");
}

let states = {};
let preferredSide = "left";
let currentVisibleStates = {};
let refreshSceneClearance = () => {};
let refreshSceneBounds = () => {};
function normalPanelWidth() {
  const width = window.innerWidth;
  return width <= 480 ? Math.min(275, Math.max(80, width - 92)) : width <= 760 ? Math.min(275, Math.max(80, width - 68)) : Math.min(340, Math.max(285, width * 0.23));
}
function visibleStates() {
  if (page !== "moon" && page !== "system") return normalizeWidgetStates(states, Object.keys(widgets));
  return fitSideWidgets(states, window.innerWidth, normalPanelWidth(), preferredSide);
}
function updateSceneClearance() { refreshSceneClearance(); }
function readState() {
  const present = Object.keys(widgets);
  let saved = {};
  try { saved = JSON.parse(sessionStorage.getItem("lse-ui-widgets:" + page) ?? "{}"); } catch { /* приватний режим */ }
  try {
    const side = sessionStorage.getItem("lse-ui-preferred:" + page);
    if (side === "left" || side === "right") preferredSide = side;
  } catch { /* приватний режим */ }
  // Режиму «розгорнуто» більше немає: старі збережені стани скидаємо до звичайного.
  for (const k of Object.keys(saved)) if (saved[k] === "expanded") saved[k] = "normal";
  return normalizeWidgetStates(saved, present);
}

function paint() {
  currentVisibleStates = visibleStates();
  const expanded = expandedWidget(currentVisibleStates);
  root.dataset.expanded = expanded || "none";
  root.dataset.leftState = currentVisibleStates.left ?? "normal";
  root.dataset.rightState = currentVisibleStates.right ?? "normal";
  for (const [side, widget] of Object.entries(widgets)) {
    const mode = currentVisibleStates[side];
    widget.target.classList.toggle("is-collapsed", mode === "collapsed");
    widget.target.classList.toggle("is-expanded", mode === "expanded");
    widget.target.dataset.state = mode;
    widget.collapse.textContent = mode === "collapsed" ? (side === "left" ? "›" : "‹") : "−";
    const collapseLabel = mode === "collapsed" ? "Відкрити панель" : "Згорнути панель";
    widget.collapse.title = collapseLabel;
    widget.collapse.setAttribute("aria-label", collapseLabel);
    widget.collapse.setAttribute("aria-expanded", String(mode !== "collapsed"));
    widget.expand.textContent = mode === "expanded" ? "◱" : "⤢";
    const expandLabel = mode === "expanded" ? "Повернути звичайну ширину" : "Розгорнути панель на пів екрана";
    widget.expand.title = expandLabel;
    widget.expand.setAttribute("aria-label", expandLabel);
    widget.expand.setAttribute("aria-pressed", String(mode === "expanded"));
  }
  // Three.js має ResizeObserver на host, а графіки — на canvas; це додаткова
  // подія для модулів, які ще використовують window.resize.
  requestAnimationFrame(() => {
    refreshSceneBounds();
    window.dispatchEvent(new Event("resize"));
  });
}

function updateState(side, action) {
  // A temporarily auto-collapsed panel can be opened by the user:
  // it becomes the preferred side and the opposite panel closes.
  states = widgetTransition(currentVisibleStates, side, action, Object.keys(widgets));
  preferredSide = side;
  paint();
  try {
    sessionStorage.setItem("lse-ui-widgets:" + page, JSON.stringify(states));
    sessionStorage.setItem("lse-ui-preferred:" + page, preferredSide);
  } catch { /* приватний режим */ }
}

// Render scene bounds follow the ACTUAL visible widget rectangles instead
// of the entire viewport. The Moon/System cameras stay centered in free space.
function initSceneGeometry() {
  if (page !== "moon" && page !== "system") return;
  const mainDock = document.querySelector("body > .ui-dock");
  const surfaceDock = document.querySelector("#surface .ui-surface-dock");
  const update = () => {
    const width = window.innerWidth;
    const gap = 10;
    const leftWidget = widgets.left?.target;
    const rightWidget = widgets.right?.target;
    const edge = (el,side) => {
      if (!el || getComputedStyle(el).display === "none") return 0;
      const r = el.getBoundingClientRect();
      return side === "left" ? Math.ceil(r.right + gap) : Math.ceil(width - r.left + gap);
    };
    const {left,right,compact} = sceneInsets(
      width, edge(leftWidget,"left"), edge(rightWidget,"right"), root.dataset.expanded, 210
    );
    const set = (key,value) => {
      if (root.style.getPropertyValue(key) !== value) root.style.setProperty(key,value);
    };
    set("--scene-left",left + "px");
    set("--scene-right",right + "px");
    root.dataset.sceneCompact = String(compact);
    const dock = root.classList.contains("surface-active") ? surfaceDock : mainDock;
    const rect = dock?.getBoundingClientRect();
    const height = rect && rect.height ? Math.ceil(rect.height) : 68;
    set("--scene-dock-height",height + "px");
    set("--scene-dock-space",Math.max(58, height + 18) + "px");
  };
  refreshSceneBounds = update;
  refreshSceneClearance = update;
  if (typeof ResizeObserver !== "undefined") {
    const observer = new ResizeObserver(() => requestAnimationFrame(update));
    for (const item of [mainDock,surfaceDock,widgets.left?.target,widgets.right?.target]) {
      if (item) observer.observe(item);
    }
  }
  window.addEventListener("resize", (event) => {
    if (event.isTrusted) paint();
    requestAnimationFrame(update);
  }, {passive:true});
  requestAnimationFrame(update);
}

function initHeaderNavigation() {
  const strip = document.getElementById("header-middle");
  const active = strip?.querySelector(".tabs [aria-current='page']");
  if (!strip || !active) return;
  const stripBox = strip.getBoundingClientRect();
  const activeBox = active.getBoundingClientRect();
  if (activeBox.right > stripBox.right) strip.scrollLeft += activeBox.right - stripBox.right + 10;
  else if (activeBox.left < stripBox.left) strip.scrollLeft -= stripBox.left - activeBox.left + 10;
}

// Кнопка ⛶: «режим фокусу» — ховає всі віджети й доки, лишається лише сцена (глобус / система).
function initFullscreen() {
  const button = document.getElementById("fullscreen-toggle");
  if (!button) return;
  if (page !== "moon" && page !== "system") { button.hidden = true; return; } // на аналітичних сторінках сцени немає
  const sync = (on) => {
    root.classList.toggle("ui-focus", on);
    button.setAttribute("aria-pressed", String(on));
    button.title = on ? "Показати віджети" : "Сховати всі віджети";
    button.setAttribute("aria-label", button.title);
    requestAnimationFrame(() => { refreshSceneBounds(); window.dispatchEvent(new Event("resize")); });
  };
  button.addEventListener("click", () => sync(!root.classList.contains("ui-focus")));
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && root.classList.contains("ui-focus")) sync(false);
  });
  sync(false);
}

function initHeaderHeight() {
  const header = document.getElementById("site-header");
  if (!header) return;
  const resize = () => {
    const height = Math.ceil(header.getBoundingClientRect().height);
    document.documentElement.style.setProperty("--header-h", height + "px");
    document.documentElement.style.setProperty("--work-h", Math.max(0, window.innerHeight - height) + "px");
  };
  if (typeof ResizeObserver !== "undefined") new ResizeObserver(resize).observe(header);
  window.addEventListener("resize", resize, { passive: true });
  resize();
}

initHeaderHeight();
initFullscreen();
if (page === "moon" && window.location.hash === "#search") {
  // Сумісність зі старими посиланнями, коли «Підбір» був під глобусом.
  window.location.replace("/search" + window.location.search);
} else if (page === "moon") initMoon();
if (page === "system") initSystem();
if (page === "search") initSearch();
if (["mission", "launch", "plan"].includes(page)) initAnalytics();
states = readState();
paint();
initSceneGeometry();
initHeaderNavigation();
// панелі розставлено; поля сцени рахуємо одразу (не чекаючи кадру, який може затриматись важкими модулями) — і показуємо інтерфейс
refreshSceneBounds();
window.__gate?.("ui");
