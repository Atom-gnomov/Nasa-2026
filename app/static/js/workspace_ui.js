// Спільна оболонка робочого простору. DOM/ID існуючих модулів НЕ замінюємо:
// переміщуємо наявні вузли до фіксованих віджетів, зберігаючи обробники та canvas.
import { expandedWidget, normalizeWidgetStates, widgetTransition } from "./workspace_state.js";

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
  actions.append(collapse, expand);
  header.append(title, actions);
  target.append(header, body);
  widgets[side] = { target, collapse, expand };
  for (const button of [collapse, expand]) {
    button.addEventListener("click", () => updateState(side, button.dataset.widgetAction));
  }
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
  for (const item of items) if (item) content.append(item);
  toggle.addEventListener("click", () => {
    dock.classList.toggle("is-collapsed");
    const open = !dock.classList.contains("is-collapsed");
    toggle.textContent = open ? "⌄" : "⌃";
    toggle.title = open ? "Згорнути налаштування" : "Розгорнути налаштування";
    toggle.setAttribute("aria-label", toggle.title);
    toggle.setAttribute("aria-expanded", String(open));
  });
  heading.append(title, toggle);
  dock.append(heading, content);
  owner.append(dock);
  return { dock, heading, content };
}

function initMoon() {
  const left = document.querySelector(".moon-layout > .side-panel");
  const right = document.getElementById("metrics-overlay");
  prepareWidget(left, "left", "Вибір місця та графіки", { scene: true });
  prepareWidget(right, "right", "Метрики", { scene: true });
  const globe = document.querySelector(".globe-wrap");
  if (!globe) return;
  const controls = [...globe.querySelectorAll(":scope > .globe-toolbar, :scope > #layer-legend, :scope > .globe-sources")];
  const { heading } = createDock("Налаштування карти", controls);
  const modes = element("div", "scene-mode-switch seg");
  for (const [mode, name] of [["globe", "Глобус"], ["surface", "Вид з поверхні"]]) {
    const button = element("button", mode === "globe" ? "active" : "", name);
    button.type = "button";
    button.dataset.sceneMode = mode;
    button.setAttribute("aria-pressed", String(mode === "globe"));
    button.addEventListener("click", () => {
      root.classList.toggle("surface-active", mode === "surface");
      for (const b of modes.querySelectorAll("button")) {
        const active = b.dataset.sceneMode === mode;
        b.classList.toggle("active", active);
        b.setAttribute("aria-pressed", String(active));
      }
      requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
    });
    modes.append(button);
  }
  heading.prepend(modes);
  // Док глобуса ховається у виді з поверхні: потрібна окрема видима
  // кнопка повернення, інакше користувач залишиться в цьому режимі.
  const surface = document.getElementById("surface");
  if (surface) {
    const back = element("button", "surface-back", "← Глобус");
    back.type = "button";
    back.title = "Повернутися до глобуса";
    back.addEventListener("click", () => modes.querySelector('[data-scene-mode="globe"]').click());
    surface.prepend(back);
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
  createDock("Налаштування системи", [toolbar, layout.querySelector("#system-note"), layout.querySelector(".globe-sources")]);
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
function readState() {
  const present = Object.keys(widgets);
  let saved = {};
  try { saved = JSON.parse(sessionStorage.getItem("lse-ui-widgets:" + page) ?? "{}"); } catch { /* приватний режим */ }
  return normalizeWidgetStates(saved, present);
}

function paint() {
  const expanded = expandedWidget(states);
  root.dataset.expanded = expanded || "none";
  root.dataset.leftState = states.left ?? "normal";
  root.dataset.rightState = states.right ?? "normal";
  for (const [side, widget] of Object.entries(widgets)) {
    const mode = states[side];
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
  requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
}

function updateState(side, action) {
  states = widgetTransition(states, side, action, Object.keys(widgets));
  paint();
  try { sessionStorage.setItem("lse-ui-widgets:" + page, JSON.stringify(states)); } catch { /* приватний режим */ }
}

function initFullscreen() {
  const button = document.getElementById("fullscreen-toggle");
  if (!button) return;
  const sync = () => {
    const active = Boolean(document.fullscreenElement);
    button.setAttribute("aria-pressed", String(active));
    button.title = active ? "Вийти з повноекранного режиму" : "Повноекранний режим";
    button.setAttribute("aria-label", button.title);
  };
  button.addEventListener("click", async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else if (document.documentElement.requestFullscreen) await document.documentElement.requestFullscreen();
    } catch { /* браузер може заборонити fullscreen */ }
    sync();
  });
  document.addEventListener("fullscreenchange", sync);
  sync();
}

function initHeaderHeight() {
  const header = document.getElementById("site-header");
  if (!header) return;
  const resize = () => document.documentElement.style.setProperty("--header-h", header.getBoundingClientRect().height + "px");
  new ResizeObserver(resize).observe(header);
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
