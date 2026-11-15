// Навігація-майстер «Планування місії» (F21, П-14): 10 кроків над наявними вкладками. Смужка в шапці показує кроки, їхній
// стан (заповнено / потребує перегляду / ще ні), веде на наявні екрани й підсвічує потрібний розділ. Вибір кожного кроку
// береться зі спільних сховищ (pipeline.js, selection.js, state.js) і вдруге не вводиться. Чисті функції — без DOM.
import { t, onLangChange } from "./i18n.js";
import { getState, subscribe } from "./state.js";
import { loadLaunch, loadSearchForm } from "./pipeline.js";
import { loadLead, loadMissionForm } from "./selection.js";

export const PLAN_KEY = "lse-mission-plan";

// href — екран, що відповідає кроку; ?step=n тримає підсвічений розділ; ready: false — крок ще не реалізовано (дивись TASKS.md).
export const STEPS = [
  { n: 1, title: "Назва й мета", path: "/moon", ready: true },
  { n: 2, title: "Тип місії", path: "/mission", ready: true },
  { n: 3, title: "Вікно запуску", path: "/launch-window", ready: true },
  { n: 4, title: "Тривалість", path: "/mission", ready: true },
  { n: 5, title: "Район і точка посадки", path: "/search", ready: true },
  { n: 6, title: "Екіпаж або техніка", path: "/mission", ready: true },
  { n: 7, title: "Корисне навантаження", path: "/mission", ready: true },
  { n: 8, title: "Носій і політ", path: "/plan", ready: true },
  { n: 9, title: "Перевірка узгодженості", path: "/consistency", ready: true },
  { n: 10, title: "Підсумковий звіт", path: "/plan", ready: false },
];
export const GOALS = [
  { id: "", label: "— не вибрано —" },
  { id: "samples", label: "Збір зразків" },
  { id: "ice", label: "Пошук води й льоду" },
  { id: "technology", label: "Випробування технологій" },
  { id: "science", label: "Наукові дослідження" },
  { id: "base", label: "Постійна база" },
];

const read = (key) => { try { return JSON.parse(globalThis.localStorage?.getItem(key) ?? "null"); } catch { return null; } };
const write = (key, value) => { try { globalThis.localStorage?.setItem(key, JSON.stringify(value)); } catch { /* не критично */ } };

export function normalizePlan(raw) {
  const out = { name: "", goal: "", confirmed: {} };
  if (!raw || typeof raw !== "object") return out;
  if (typeof raw.name === "string") out.name = raw.name.slice(0, 80);
  if (GOALS.some((g) => g.id === raw.goal)) out.goal = raw.goal;
  if (raw.confirmed && typeof raw.confirmed === "object") {
    for (const [k, v] of Object.entries(raw.confirmed)) if (/^([1-9]|10)$/.test(k) && typeof v === "string") out.confirmed[k] = v;
  }
  return out;
}
export const loadPlan = () => normalizePlan(read(PLAN_KEY));
export const savePlan = (plan) => write(PLAN_KEY, normalizePlan(plan));

// Дані, від яких залежить крок (беруться зі спільних сховищ): змінились після підтвердження — крок «потребує перегляду».
// ctx: { plan, mission (lse-mission), search (lse-search), launch (lse-launch), lead (lse-plan-lead), state (state.js) }
export function stepData(n, ctx) {
  const { plan = {}, mission = null, search = null, launch = {}, lead = null, state = {} } = ctx;
  switch (n) {
    case 1: return { name: plan.name || "", goal: plan.goal || "" };
    case 2: return { crewed: Boolean(mission?.crewed) };
    case 3: return { date: String(state.datetime ?? "").slice(0, 10), trajectory: launch.trajectory ?? "any", departure: launch.departure ?? "" };
    case 4: return { crewed: Boolean(mission?.crewed), days: mission?.days ?? null };
    case 5: return { lat: state.lat ?? null, lon: state.lon ?? null, site: state.site ?? null,
                     requirements: search ? { days: search.days, regionKey: search.regionKey, minSunHours: search.minSunHours,
                       minCommHours: search.minCommHours, maxSlopeDeg: search.maxSlopeDeg, minEarthPct: search.minEarthPct,
                       minSunPct: search.minSunPct, priorities: (search.priorities ?? []).filter((p) => p.on).map((p) => p.id) } : null };
    case 6: return { crewed: Boolean(mission?.crewed), crew: mission?.crew ?? null, bio: Boolean(mission?.useBio),
                     members: mission?.useBio ? mission.members : null };
    case 7: return { sizes: mission?.sizes ?? null };
    case 8: return { site: launch.site || lead?.siteId || "", vehicle: launch.vehicle ?? "any", trajectory: launch.trajectory ?? "any" };
    // перевірка й звіт залежать від усіх виборів: змінились після підтвердження — потребують перегляду
    case 9: return [1, 2, 3, 4, 5, 6, 7, 8].map((k) => stepData(k, ctx));
    case 10: return stepData(9, ctx);
    default: return {};
  }
}
export const signature = (data) => JSON.stringify(data);

// Чи вже щось обрано на кроці (для підказки «заповніть»): порожній крок не можна «підтвердити» з нічого.
export function stepFilled(n, ctx) {
  const d = stepData(n, ctx);
  switch (n) {
    case 1: return Boolean(d.goal);
    case 2: return ctx.mission != null;
    case 3: return Boolean(d.date);
    case 4: return d.days != null;
    case 5: return d.lat != null && d.lon != null;
    case 6: return ctx.mission != null;
    case 7: return d.sizes != null;
    case 8: return Boolean(d.site);
    case 9: return true; // перевірку можна запустити будь-коли
    default: return false;
  }
}

// "done" — підтверджено і дані не змінились; "review" — підтверджено, але дані змінились; "todo" — ще ні.
export function stepStatus(n, ctx) {
  const saved = ctx.plan?.confirmed?.[String(n)];
  if (!saved) return "todo";
  return saved === signature(stepData(n, ctx)) ? "done" : "review";
}

export function confirmStep(n, ctx) {
  const plan = normalizePlan(ctx.plan);
  plan.confirmed[String(n)] = signature(stepData(n, ctx));
  return plan;
}

export const nextStep = (n) => (STEPS.find((s) => s.n === n + 1 && s.ready) ? n + 1 : null);
export const prevStep = (n) => (n > 1 ? n - 1 : null);

// Крок за адресою: явний ?step=n, інакше типовий для сторінки (Підбір — 5, Місія — 2, План і «Система» — 8, Вікно запуску — 3).
export function stepFromLocation(pathname, search = "", hash = "") {
  const m = /[?&]step=(\d{1,2})\b/.exec(search);
  if (m && Number(m[1]) >= 1 && Number(m[1]) <= STEPS.length) return Number(m[1]);
  if (pathname === "/moon") return hash === "#search" ? 5 : null;
  return { "/search": 5, "/mission": 2, "/plan": 8, "/system": 8, "/launch-window": 3, "/consistency": 9 }[pathname] ?? null;
}

// Адреса кроку зі збереженням решти параметрів (дата, мова…).
export function stepHref(step, search = "") {
  const params = new URLSearchParams(search);
  params.set("step", String(step.n));
  const hash = step.path === "/search" ? "#search" : "";
  return `${step.path}?${params}${hash}`;
}

// Зведення «Мій план»: [[назва, значення], …] для заповнених полів.
export function summaryRows(ctx) {
  const { plan = {}, mission = null, search = null, launch = {}, lead = null, state = {} } = ctx;
  const rows = [];
  if (plan.name) rows.push(["Назва", plan.name]);
  const goal = GOALS.find((g) => g.id === plan.goal);
  if (goal?.id) rows.push(["Мета", goal.label]);
  if (mission) {
    rows.push(["Тип", mission.crewed ? "пілотована" : "безпілотна"]);
    if (mission.crewed) rows.push(["Екіпаж", `${mission.useBio ? (mission.members?.length ?? 0) : (mission.crew ?? "за профілем")} осіб, ${mission.days} діб`]);
  }
  if (state.datetime) rows.push(["Дата", String(state.datetime).slice(0, 10)]);
  if (state.lat != null && state.lon != null) rows.push(["Точка посадки", `${Number(state.lat).toFixed(2)}°, ${Number(state.lon).toFixed(2)}°`]);
  if (search) rows.push(["Період пошуку", `${search.days} діб`]);
  const site = launch.site || lead?.siteId;
  if (site) rows.push(["Майданчик", site.startsWith("auto:") ? "оптимальний" : site]);
  if (launch.departure) rows.push(["Дата старту", launch.departure]);
  if (launch.vehicle && launch.vehicle !== "any") rows.push(["Ракета", launch.vehicle]);
  if (launch.trajectory && launch.trajectory !== "any") rows.push(["Траєкторія", launch.trajectory === "direct" ? "пряма" : "найекономніша"]);
  return rows.map(([k, v]) => [t(k), v]);
}

// ---- DOM ----------------------------------------------------------------------------------------------------------
export function buildContext(plan = loadPlan()) {
  return { plan, mission: loadMissionForm(), search: loadSearchForm(), launch: loadLaunch(), lead: loadLead(), state: getState() };
}

function init() {
  const bar = document.getElementById("mp-steps");
  if (!bar) return;
  const chips = bar.querySelector(".mp-chips");
  const nav = bar.querySelector(".mp-nav");
  const sumBox = bar.querySelector(".mp-summary-rows");
  const pop = bar.querySelector(".mp-goal");
  let plan = loadPlan();
  const current = () => stepFromLocation(location.pathname, location.search, location.hash);
  const ICON = { done: "✓", review: "!", todo: "" };

  function render() {
    const ctx = buildContext(plan);
    const cur = current();
    chips.replaceChildren(...STEPS.map((step) => {
      const status = stepStatus(step.n, ctx);
      const a = document.createElement(step.ready ? "a" : "span");
      a.className = `mp-chip ${status}${cur === step.n ? " current" : ""}${step.ready ? "" : " soon"}`;
      if (step.ready) a.href = stepHref(step, location.search); else a.title = t("Скоро: цей крок ще розробляється");
      if (cur === step.n) a.setAttribute("aria-current", "step");
      const num = Object.assign(document.createElement("b"), { textContent: ICON[status] || String(step.n) });
      a.append(num, " ", Object.assign(document.createElement("span"), { textContent: t(step.title) }));
      if (status === "review") a.title = t("Дані змінились після підтвердження — перегляньте крок");
      if (step.n === 1) a.addEventListener("click", (ev) => { if (cur === 1 || !pop.hidden) { ev.preventDefault(); pop.hidden = !pop.hidden; } });
      return a;
    }));
    const prev = cur ? prevStep(cur) : null, next = cur ? nextStep(cur) : null;
    nav.hidden = !cur;
    const prevBtn = nav.querySelector(".mp-prev"), nextBtn = nav.querySelector(".mp-next");
    prevBtn.disabled = !prev;
    nextBtn.disabled = !cur;
    nextBtn.textContent = next ? t("Підтвердити й далі ›") : t("Підтвердити");
    const rows = summaryRows(ctx);
    sumBox.replaceChildren(...rows.flatMap(([k, v]) => [Object.assign(document.createElement("dt"), { textContent: k }),
      Object.assign(document.createElement("dd"), { textContent: v })]));
    bar.querySelector(".mp-summary-empty").hidden = rows.length > 0;
    highlight(cur);
  }

  function highlight(cur) {
    for (const el of document.querySelectorAll(".mp-focus")) el.classList.remove("mp-focus");
    if (!cur) return;
    const targets = [...document.querySelectorAll("[data-step]")].filter((el) => el.dataset.step.split(/\s+/).includes(String(cur)));
    for (const el of targets) el.classList.add("mp-focus");
    targets[0]?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }

  const go = (n) => { const step = STEPS.find((x) => x.n === n); if (step?.ready) location.href = stepHref(step, location.search); };
  nav.querySelector(".mp-prev").addEventListener("click", () => { const cur = current(); if (cur) go(prevStep(cur)); });
  nav.querySelector(".mp-next").addEventListener("click", () => {
    const cur = current();
    if (!cur) return;
    plan = confirmStep(cur, buildContext(plan));
    savePlan(plan);
    const next = nextStep(cur);
    if (next) go(next); else render();
  });

  // Крок 1: назва й мета (адмінпараметр і мета; мета далі підставлятиме типові вибори — F22)
  const nameInput = pop.querySelector(".mp-name"), goalSel = pop.querySelector(".mp-goal-select");
  goalSel.replaceChildren(...GOALS.map((g) => new Option(t(g.label), g.id)));
  nameInput.value = plan.name;
  goalSel.value = plan.goal;
  nameInput.addEventListener("input", () => { plan = { ...plan, name: nameInput.value }; savePlan(plan); render(); });
  goalSel.addEventListener("change", () => { plan = { ...plan, goal: goalSel.value }; savePlan(plan); render(); });
  pop.querySelector(".mp-goal-close").addEventListener("click", () => { pop.hidden = true; });
  if (current() === 1) pop.hidden = false;

  render();
  subscribe(render);
  window.addEventListener("storage", () => { plan = loadPlan(); render(); });
  window.addEventListener("pageshow", () => { plan = loadPlan(); render(); });
  onLangChange(() => { goalSel.replaceChildren(...GOALS.map((g) => new Option(t(g.label), g.id))); goalSel.value = plan.goal; render(); });
}

if (typeof document !== "undefined") init();
