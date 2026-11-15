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
  // Дата й місце посадки — одне ціле: крок 3 лишається лише як псевдонім кроку 5 (календар і точка — на одному екрані)
  { n: 3, title: "Дата посадки", path: "/moon", ready: true, mergedInto: 5 },
  { n: 4, title: "Тривалість", path: "/mission", ready: true, onlyCrewed: true }, // без людей тривалість не потрібна
  { n: 5, title: "Район, дата й точка посадки", path: "/search", ready: true },
  { n: 6, title: "Екіпаж або техніка", path: "/mission", ready: true },
  { n: 7, title: "Корисне навантаження", path: "/mission", ready: true },
  { n: 8, title: "Носій і політ", path: "/plan", ready: true },
  { n: 9, title: "Перевірка узгодженості", path: "/consistency", ready: true },
  { n: 10, title: "Підсумковий звіт", path: "/report", ready: true },
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
    case 3: return { date: String(state.datetime ?? "").slice(0, 10) };
    case 4: return { crewed: Boolean(mission?.crewed), days: mission?.days ?? null };
    case 5: return { date: String(state.datetime ?? "").slice(0, 10), lat: state.lat ?? null, lon: state.lon ?? null, site: state.site ?? null,
                     requirements: search ? { days: search.days, regionKey: search.regionKey, minSunHours: search.minSunHours,
                       minCommHours: search.minCommHours, maxSlopeDeg: search.maxSlopeDeg, minEarthPct: search.minEarthPct,
                       minSunPct: search.minSunPct, priorities: (search.priorities ?? []).filter((p) => p.on).map((p) => p.id) } : null };
    case 6: return { crewed: Boolean(mission?.crewed), crew: mission?.crew ?? null, bio: Boolean(mission?.useBio),
                     members: mission?.useBio ? mission.members : null };
    case 7: return { sizes: mission?.sizes ?? null, items: mission?.equipmentItems ?? null, categoryKg: mission?.categoryKg ?? null };
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
    case 5: return d.lat != null && d.lon != null && Boolean(d.date);
    case 6: return ctx.mission != null;
    case 7: return d.sizes != null;
    case 8: return Boolean(d.site);
    case 9: case 10: return true; // перевірка й звіт — похідні від виборів, їх можна відкрити будь-коли
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

// Кроки, видимі у смузі: без злитих і без «Тривалості» для безпілотної місії. Номер на кнопці — місце в цьому списку.
export const stepVisible = (step, mission) => step.ready && !step.mergedInto && !(step.onlyCrewed && !mission?.crewed);
export const visibleSteps = (mission) => STEPS.filter((s) => stepVisible(s, mission));
export const displayNumber = (n, mission) => visibleSteps(mission).findIndex((s) => s.n === n) + 1;
export const canonicalStep = (n) => STEPS.find((s) => s.n === n)?.mergedInto ?? n;

export function nextStep(n, mission = null) {
  const list = visibleSteps(mission);
  const i = list.findIndex((s) => s.n === canonicalStep(n));
  return i >= 0 && i + 1 < list.length ? list[i + 1].n : null;
}
export function prevStep(n, mission = null) {
  const list = visibleSteps(mission);
  const i = list.findIndex((s) => s.n === canonicalStep(n));
  return i > 0 ? list[i - 1].n : null;
}

// Крок за адресою: явний ?step=n, інакше типовий для сторінки (Підбір — 5, Місія — 2, План і «Система» — 8).
export function stepFromLocation(pathname, search = "", hash = "") {
  const m = /[?&]step=(\d{1,2})\b/.exec(search);
  if (m && Number(m[1]) >= 1 && Number(m[1]) <= STEPS.length) return canonicalStep(Number(m[1]));
  if (pathname === "/moon") return hash === "#search" ? 5 : null;
  return { "/search": 5, "/mission": 2, "/plan": 8, "/system": 8, "/consistency": 9, "/report": 10 }[pathname] ?? null;
}

// ---- Мета місії → типові вибори наступних кроків (F22; дані — GET /api/mission-goals, M25) ------------------------------
const FACTOR_NAMES = { energy: "Енергія", comms: "Зв'язок", radiation: "Радіація", temperature: "Температура" };
const SEARCH_ORDER = ["energy", "comms", "radiation", "temperature"];

// Що мета підставляє: «Місія» (тип, тривалість перебування) і «Підбір» (порядок пріоритетів). Повертає нові значення сховищ і
// перелік змін для користувача. Ручні вибори не зберігаються лише для цих полів — це явна дія зміни мети.
export function applyGoalDefaults(goal, mission, search) {
  if (!goal?.defaults) return { mission, search, changes: [] };
  const d = goal.defaults;
  const crewed = d.mission_profile === "crewed";
  const nextMission = { ...(mission ?? {}), crewed, days: d.stay_days };
  if (!crewed) { nextMission.crew = null; nextMission.useBio = false; }
  const known = (search?.priorities ?? SEARCH_ORDER.map((id) => ({ id, on: false }))).map((p) => p.id);
  const rest = SEARCH_ORDER.filter((id) => !d.priorities.includes(id) && known.includes(id) || (!known.length && !d.priorities.includes(id)));
  const priorities = [...d.priorities.map((id) => ({ id, on: true })), ...rest.map((id) => ({ id, on: false }))];
  const nextSearch = { ...(search ?? {}), priorities };
  const changes = [
    `${t("Тип місії")}: ${t(crewed ? "пілотована" : "безпілотна")}`,
    `${t("Тривалість перебування")}: ${d.stay_days} ${t("діб")}`,
    `${t("Пріоритети «Підбору»")}: ${d.priorities.map((id) => t(FACTOR_NAMES[id] ?? id)).join(" › ")}`,
  ];
  return { mission: nextMission, search: nextSearch, changes };
}

// Чи належить елемент із атрибутом data-step (напр. "2 4 6") кроку n.
export const stepMatches = (attr, n) => String(attr ?? "").split(/\s+/).includes(String(n));

// Фокус на кроці: елемент ховаємо, якщо він сам не для цього кроку й у ньому немає вкладених елементів цього кроку.
export const hiddenInFocus = (ownAttr, hasMatchingDescendant, n) => !stepMatches(ownAttr, n) && !hasMatchingDescendant;

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
  const showAllBtn = bar.querySelector(".mp-showall");
  const sumBox = document.querySelector(".mp-summary-rows");
  const pop = document.querySelector(".mp-goal");
  let plan = loadPlan();
  const current = () => stepFromLocation(location.pathname, location.search, location.hash);
  const ICON = { done: "✓", review: "!", todo: "" };

  function render() {
    let ctx = buildContext(plan);
    const cur = current();
    // кнопки «підтвердити й далі» немає: крок, на якому ви зараз і який заповнено, вважається переглянутим;
    // якщо потім його вибори зміняться деінде — він отримає позначку «потребує перегляду»
    if (cur && stepFilled(cur, ctx) && stepStatus(cur, ctx) !== "done") {
      plan = confirmStep(cur, ctx);
      savePlan(plan);
      ctx = buildContext(plan);
    }
    chips.replaceChildren(...visibleSteps(ctx.mission).map((step) => {
      const status = stepStatus(step.n, ctx);
      const a = document.createElement(step.ready ? "a" : "span");
      a.className = `mp-chip ${status}${cur === step.n ? " current" : ""}${step.ready ? "" : " soon"}`;
      if (step.ready) a.href = stepHref(step, location.search); else a.title = t("Скоро: цей крок ще розробляється");
      if (cur === step.n) a.setAttribute("aria-current", "step");
      const num = Object.assign(document.createElement("b"), { textContent: ICON[status] || String(displayNumber(step.n, ctx.mission)) });
      a.append(num, " ", Object.assign(document.createElement("span"), { textContent: t(step.title) }));
      if (status === "review") a.title = t("Дані змінились після підтвердження — перегляньте крок");
      if (step.n === 1) a.addEventListener("click", (ev) => { if (cur === 1 || !pop.hidden) { ev.preventDefault(); pop.hidden = !pop.hidden; } });
      return a;
    }));
    const rows = summaryRows(ctx);
    sumBox.replaceChildren(...rows.flatMap(([k, v]) => [Object.assign(document.createElement("dt"), { textContent: k }),
      Object.assign(document.createElement("dd"), { textContent: v })]));
    document.querySelector(".mp-summary-empty").hidden = rows.length > 0;
    highlight(cur);
  }

  // Прохід майстром: на тій самій вкладці для кожного кроку видно лише потрібне налаштування (решту можна показати кнопкою)
  const explicitStep = () => /[?&]step=\d/.test(location.search);
  let showAll = false;
  function highlight(cur) {
    for (const el of document.querySelectorAll(".mp-focus")) el.classList.remove("mp-focus");
    for (const el of document.querySelectorAll(".mp-hidden")) el.classList.remove("mp-hidden");
    if (!cur) return;
    const all = [...document.querySelectorAll("[data-step]")];
    const targets = all.filter((el) => stepMatches(el.dataset.step, cur));
    for (const el of targets) el.classList.add("mp-focus");
    const focusMode = explicitStep() && !showAll && targets.length > 0;
    if (focusMode) {
      for (const el of all) {
        if (hiddenInFocus(el.dataset.step, el.querySelector(stepSelector(cur)) !== null, cur)) el.classList.add("mp-hidden");
      }
    }
    document.body.classList.toggle("mp-focus-mode", focusMode);
    if (explicitStep() && cur) document.body.dataset.mpStep = String(cur); else delete document.body.dataset.mpStep;
    const toggle = showAllBtn;
    toggle.hidden = !(explicitStep() && targets.length > 0);
    toggle.setAttribute("aria-pressed", String(showAll));
    toggle.textContent = showAll ? t("Лише цей крок") : t("Усі налаштування");
    targets[0]?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }
  const stepSelector = (n) => `[data-step~="${n}"]`;

  showAllBtn.addEventListener("click", () => { showAll = !showAll; highlight(current()); });

  // Крок 1: назва й мета (адмінпараметр і мета; мета далі підставлятиме типові вибори — F22)
  const nameInput = pop.querySelector(".mp-name"), goalSel = pop.querySelector(".mp-goal-select");
  goalSel.replaceChildren(...GOALS.map((g) => new Option(t(g.label), g.id)));
  nameInput.value = plan.name;
  goalSel.value = plan.goal;
  nameInput.addEventListener("input", () => { plan = { ...plan, name: nameInput.value }; savePlan(plan); render(); });
  const goalInfo = pop.querySelector(".mp-goal-info");
  let goalCatalog = null;
  const loadGoals = async () => {
    if (goalCatalog) return goalCatalog;
    try { goalCatalog = (await (await fetch("/api/mission-goals")).json()).goals ?? []; } catch { goalCatalog = []; }
    return goalCatalog;
  };
  const showGoal = async (applied) => {
    const goal = (await loadGoals()).find((g) => g.id === plan.goal);
    goalInfo.replaceChildren();
    document.querySelectorAll(".mp-goal-site-notes").forEach((el) => { el.hidden = !goal; el.replaceChildren(); });
    if (!goal) return;
    const lang = document.documentElement.lang;
    goalInfo.append(Object.assign(document.createElement("p"), { className: "muted small", textContent: lang === "en" ? goal.name_en : goal.summary }));
    if (applied?.length) {
      goalInfo.append(Object.assign(document.createElement("p"), { className: "small", textContent: `${t("Підставлено метою")}: ${applied.join("; ")}.` }));
    }
    for (const el of document.querySelectorAll(".mp-goal-site-notes")) { // крок 5: критерії до місця за метою
      el.append(Object.assign(document.createElement("strong"), { textContent: `${t("Критерії до місця")}: ${lang === "en" ? goal.name_en : goal.name}` }));
      const ul = document.createElement("ul");
      for (const note of goal.site_notes) ul.append(Object.assign(document.createElement("li"), { textContent: note }));
      el.append(ul);
    }
  };
  goalSel.addEventListener("change", async () => {
    plan = { ...plan, goal: goalSel.value };
    savePlan(plan);
    const goal = (await loadGoals()).find((g) => g.id === plan.goal);
    let applied = [];
    if (goal) { // мета підставляє тип, тривалість і пріоритети «Підбору»
      const out = applyGoalDefaults(goal, loadMissionForm(), loadSearchForm());
      try {
        localStorage.setItem("lse-mission", JSON.stringify(out.mission));
        localStorage.setItem("lse-search", JSON.stringify(out.search));
      } catch { /* сховище недоступне */ }
      applied = out.changes;
    }
    await showGoal(applied);
    render();
    // сторінки, що тримають форму в пам'яті, перечитують підставлене
    if (applied.length && (location.pathname === "/mission" || location.pathname === "/search" || location.hash === "#search")) location.reload();
  });
  showGoal();
  pop.querySelector(".mp-goal-close").addEventListener("click", () => { pop.hidden = true; });
  if (current() === 1) pop.hidden = false;

  render();
  subscribe(render);
  window.addEventListener("storage", () => { plan = loadPlan(); render(); });
  window.addEventListener("lse-mission-changed", render);
  window.addEventListener("pageshow", () => { plan = loadPlan(); render(); });
  onLangChange(() => { goalSel.replaceChildren(...GOALS.map((g) => new Option(t(g.label), g.id))); goalSel.value = plan.goal; render(); });
}

if (typeof document !== "undefined") init();
