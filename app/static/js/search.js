// Модуль «Підбір точок» (вкладка «Підбір», F6): вимоги, пріоритети перетягуванням, режим мін-макс, результати.
// Робить POST /api/search (контракт SearchRequest / SearchResponse, docs/MATH.md §19): сервер будує сітку кандидатів
// у регіоні, оцінює кожну за ваговими факторами й повертає найкращі зі станцією DSN для кожної.
// Дата початку береться зі спільного календаря (state.js), кінець = початок + «довжина періоду».
// Чисті функції (без DOM) експортовано й покрито tests/js/test_search.mjs.
import { publishHighlights } from "./highlights.js";
import { getState, setState } from "./state.js";

const DAY_MS = 86_400_000;
export const STORAGE_KEY = "lse-search";

// Фактори, які вміє оцінювати сервер (RankFactor). Температуру вмикаємо лише коли є дані Diviner (/api/meta).
export const FACTORS = [
  { id: "energy", label: "Енергія", hint: "освітленість і довжина найдовшої ночі: менші акумулятори" },
  { id: "comms", label: "Зв'язок", hint: "частка часу зв'язку з DSN і довжина найдовшого розриву" },
  { id: "radiation", label: "Радіація", hint: "екранування неба рельєфом: менша доза космічних променів" },
  { id: "temperature", label: "Температура", hint: "частка місячної доби в робочому діапазоні (потрібні дані Diviner)", needsData: "diviner" },
];
export const FACTOR_LABELS = Object.fromEntries(FACTORS.map((f) => [f.id, f.label]));

// Готові області пошуку. Кроки підібрано так, щоб кандидатів було ≲ 200 (ліміт сервера — 400).
export const REGIONS = {
  pole: { label: "Південний полюс, 80–90°", region: { lat_min: -90, lat_max: -80 }, grid_step_deg: 2 },
  polar: { label: "Приполярна область, 60–90° пд. ш.", region: { lat_min: -90, lat_max: -60 }, grid_step_deg: 5 },
  whole: { label: "Уся Місяць (грубо)", region: { lat_min: -90, lat_max: 90 }, grid_step_deg: 15 },
  custom: { label: "Власна область…", region: { lat_min: -90, lat_max: -80 }, grid_step_deg: 2 },
};

export const DEFAULT_FORM = {
  days: 30,
  regionKey: "pole",
  custom: { lat_min: -90, lat_max: -80, grid_step_deg: 2 },
  minSunHours: 0,
  minCommHours: 0,
  priorities: [
    { id: "energy", on: true },
    { id: "comms", on: true },
    { id: "radiation", on: false },
    { id: "temperature", on: false },
  ],
  mode: "weighted",
  includeCatalog: true,
  heightM: 0,
  limit: 20,
};

const isoZ = (ms) => new Date(ms).toISOString().slice(0, 19) + "Z";
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

/** Максимум для повзунків «години»: весь період у годинах. */
export const maxHours = (days) => Math.round(days * 24);

/** Після зміни довжини періоду значення повзунків не мають перевищувати нову межу. */
export function clampHours(form) {
  const max = maxHours(form.days);
  return { ...form, minSunHours: clamp(form.minSunHours, 0, max), minCommHours: clamp(form.minCommHours, 0, max) };
}

/** Фактори, що враховуються, у порядку важливості (порядок блоків = порядок ваг). */
export const activePriorities = (items) => items.filter((p) => p.on).map((p) => p.id);

/** Переставляє блок пріоритету з позиції `from` на `to` (перетягування або кнопки ↑ ↓); повертає новий масив. */
export function movePriority(items, from, to) {
  if (from === to || from < 0 || to < 0 || from >= items.length || to >= items.length) return items;
  const next = items.slice();
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

/** Тіло POST /api/search зі стану форми. Нульові повзунки не надсилаються (вимоги немає). */
export function buildSearchRequest(form, datetime) {
  const priorities = activePriorities(form.priorities);
  if (!priorities.length) throw new Error("Виберіть щонайменше один фактор");
  const startMs = Date.parse(datetime);
  if (!Number.isFinite(startMs)) throw new Error("Некоректна дата початку");
  const preset = REGIONS[form.regionKey] ?? REGIONS.pole;
  const custom = form.regionKey === "custom";
  const region = custom ? { lat_min: form.custom.lat_min, lat_max: form.custom.lat_max } : preset.region;
  const body = {
    start: isoZ(startMs),
    end: isoZ(startMs + form.days * DAY_MS),
    region: { ...region },
    grid_step_deg: custom ? form.custom.grid_step_deg : preset.grid_step_deg,
    priorities,
    mode: form.mode,
    include_catalog: Boolean(form.includeCatalog),
    height_m: form.heightM,
    limit: form.limit,
  };
  if (form.minSunHours > 0) body.min_sun_hours = form.minSunHours;
  if (form.minCommHours > 0) body.min_comm_hours = form.minCommHours;
  return body;
}

// ---------- Показ результатів ----------
const fmt1 = (v) => (Math.round(v * 10) / 10).toString();
export const hoursText = (h) => (h >= 48 ? `${Math.round(h)} год (${fmt1(h / 24)} доби)` : `${fmt1(h)} год`);
export const percent = (v) => `${Math.round(v * 100)} %`;
/** Короткий запис годин для клітинок таблиці (повний — у hoursText). */
export const hoursShort = (h) => `${Math.round(h)} год`;
const coord = (v) => `${Math.abs(v).toFixed(2)}°`;

/** Підпис місця: назва з каталогу або координати. */
export function placeLabel(site) {
  if (site.name) return site.name;
  return `${coord(site.lat)} ${site.lat < 0 ? "пд." : "пн."} ш., ${coord(site.lon)} ${site.lon < 0 ? "зх." : "сх."} д.`;
}

const VIOLATIONS = { min_sun_hours: "Сонця", min_comm_hours: "зв'язку" };
export const violationText = (v) => `годин ${VIOLATIONS[v.requirement] ?? v.requirement}: ${hoursText(v.value)} із потрібних ${hoursText(v.required)}`;

/** Рядки таблиці результатів для відповіді /api/search. Лише готовий текст і числа — без DOM. */
export function resultRows(response) {
  return response.chains.map((c) => ({
    rank: c.rank,
    place: placeLabel(c.moon_site),
    site: c.moon_site,
    scorePct: c.score_pct,
    factors: response.priorities.map((id) => ({ id, label: FACTOR_LABELS[id] ?? id, value: c.factors[id] })),
    sun: hoursShort(c.summary.sun_hours),
    comm: hoursShort(c.summary.comm_hours),
    station: c.dsn_station_id ? `${c.dsn_station_id} · ${hoursShort(c.dsn_hours)}` : "—",
    feasible: c.feasible,
    violations: c.violations.map(violationText),
    pareto: c.pareto,
  }));
}

/** Пояснення порівняння найкращої точки з другою простою мовою. */
export function describeComparison(cmp, labels = FACTOR_LABELS) {
  if (!cmp) return "";
  const name = (id) => (labels[id] ?? id).toLowerCase();
  const wins = (side) => cmp.per_factor.filter((f) => f.winner === side).map((f) => name(f.factor));
  const delta = Math.abs(cmp.score_delta_pct).toFixed(1);
  switch (cmp.dominance) {
    case "a":
      return `Найкраща точка не гірша за другу за жодним фактором і краща за: ${wins("a").join(", ")} (+${delta} п.).`;
    case "b":
      return `Друга точка не гірша за найкращу за жодним фактором і краща за: ${wins("b").join(", ")}; найкращою її робить лише порядок пріоритетів.`;
    case "tie":
      return "Найкраща й друга точки практично однакові за всіма факторами.";
    default: {
      const decisive = cmp.decisive_factor ? ` Вирішальний фактор — ${name(cmp.decisive_factor)}.` : "";
      return `Компроміс: найкраща виграє за ${wins("a").join(", ")}, але програє за ${wins("b").join(", ")} (+${delta} п. через пріоритети).${decisive}`;
    }
  }
}

/** Точки результатів для підсвічування на глобусі (rank 1 — найкраща; недопустимі позначено окремо). */
export const highlightPoints = (response) => response.chains.map((c) => ({
  lat: c.moon_site.lat, lon: c.moon_site.lon, rank: c.rank, feasible: c.feasible,
}));

/** Чи налаштований на сервері сервіс порад ШІ: за /api/meta (джерело "llm"). Блок порад видно завжди (рішення 2026-11-14). */
export function adviceState(meta) {
  const on = (meta?.data_sources ?? []).some((s) => s.id === "llm");
  return on
    ? { enabled: true, note: "" }
    : { enabled: false, note: "Поради ШІ вимкнені: сервер не налаштований (задайте LSE_LLM_BASE_URL, LSE_LLM_MODEL і ключ у .env)." };
}

/** Факти для POST /api/advice: готові результати пошуку (лише числа й підписи з відповіді сервера). */
export function buildAdviceFacts(response, form, top = 5) {
  const limitFields = (c) => ({
    rank: c.rank,
    place: placeLabel(c.moon_site),
    lat: c.moon_site.lat,
    lon: c.moon_site.lon,
    score_pct: c.score_pct,
    feasible: c.feasible,
    violations: c.violations,
    factors: c.factors,
    sun_hours: c.summary.sun_hours,
    comm_hours: c.summary.comm_hours,
    dsn_station_id: c.dsn_station_id,
    dsn_hours: c.dsn_hours,
  });
  const cmp = response.comparison;
  return {
    period: response.period,
    mode: response.mode,
    priorities: response.priorities,
    weights: response.weights,
    requirements: { min_sun_hours: form.minSunHours || null, min_comm_hours: form.minCommHours || null },
    candidates: { evaluated: response.grid.evaluated, total: response.grid.candidates, truncated: response.grid.truncated },
    top: response.chains.slice(0, top).map(limitFields),
    comparison: cmp && {
      dominance: cmp.dominance,
      decisive_factor: cmp.decisive_factor,
      score_delta_pct: cmp.score_delta_pct,
      per_factor: cmp.per_factor,
    },
  };
}

export function gridNote(grid) {
  const base = `Оцінено ${grid.evaluated} з ${grid.candidates} кандидатів (крок сітки ${grid.step_deg}°).`;
  return grid.truncated ? `${base} Бюджет часу сервера вичерпано: зменште область, збільште крок сітки або скоротіть період.` : base;
}

// ---------- Інтерфейс (вкладка «Підбір», search.html) ----------
const root = typeof document === "undefined" ? null : document.getElementById("search");
if (root) {
  const $ = (id) => root.querySelector(id);
  const el = {
    days: $("#s-days"), region: $("#s-region"), customBox: $("#s-custom"), latMin: $("#s-lat-min"), latMax: $("#s-lat-max"),
    step: $("#s-step"), sun: $("#s-sun"), sunOut: $("#s-sun-out"), comm: $("#s-comm"), commOut: $("#s-comm-out"),
    list: $("#s-priorities"), mode: root.querySelectorAll("[data-mode]"), catalog: $("#s-catalog"), height: $("#s-height"),
    run: $("#s-run"), status: $("#s-status"), note: $("#s-note"), compare: $("#s-compare"),
    table: $("#s-table"), body: $("#s-table tbody"), head: $("#s-head"),
    advice: $("#s-advice"), adviceAsk: $("#s-advice-ask"), adviceQuestion: $("#s-advice-question"),
    adviceAudience: $("#s-advice-audience"), adviceOut: $("#s-advice-out"), adviceStatus: $("#s-advice-status"),
  };
  let lastResponse = null;

  let form = structuredClone(DEFAULT_FORM);
  try { Object.assign(form, JSON.parse(localStorage.getItem(STORAGE_KEY)) ?? {}); } catch { /* приватний режим */ }
  let abort = null;
  let dragFrom = null;
  let available = new Set(); // джерела даних, які сервер оголосив у /api/meta

  const save = () => { try { localStorage.setItem(STORAGE_KEY, JSON.stringify(form)); } catch { /* ігноруємо */ } };
  const showStatus = (text, bad = false) => { el.status.textContent = text; el.status.hidden = !text; el.status.classList.toggle("bad", bad); };

  function renderSliders() {
    form = clampHours(form);
    const max = maxHours(form.days);
    for (const [input, out, value] of [[el.sun, el.sunOut, form.minSunHours], [el.comm, el.commOut, form.minCommHours]]) {
      input.max = String(max);
      input.value = String(value);
      out.textContent = value ? `не менше ${hoursText(value)} (${percent(value / max)} періоду)` : "без вимоги";
    }
  }

  function renderPriorities() {
    el.list.replaceChildren();
    form.priorities.forEach((p, i) => {
      const factor = FACTORS.find((f) => f.id === p.id);
      const locked = factor.needsData && !available.has(factor.needsData);
      const li = document.createElement("li");
      li.draggable = true;
      li.dataset.index = String(i);
      li.className = `prio${p.on && !locked ? "" : " off"}`;
      const check = Object.assign(document.createElement("input"), { type: "checkbox", checked: p.on && !locked, disabled: locked });
      check.setAttribute("aria-label", `Враховувати: ${factor.label}`);
      check.addEventListener("change", () => { form.priorities[i].on = check.checked; save(); renderPriorities(); });
      const text = document.createElement("span");
      text.className = "prio-text";
      const title = document.createElement("strong");
      title.textContent = `${i + 1}. ${factor.label}`;
      const hint = document.createElement("small");
      hint.textContent = locked ? "немає даних Diviner — запустіть tools/build_temperature_data.py" : factor.hint;
      text.append(title, hint);
      const up = Object.assign(document.createElement("button"), { type: "button", textContent: "↑", title: "Важливіше" });
      const down = Object.assign(document.createElement("button"), { type: "button", textContent: "↓", title: "Менш важливо" });
      up.setAttribute("aria-label", `${factor.label}: важливіше`);
      down.setAttribute("aria-label", `${factor.label}: менш важливо`);
      up.addEventListener("click", () => { form.priorities = movePriority(form.priorities, i, i - 1); save(); renderPriorities(); });
      down.addEventListener("click", () => { form.priorities = movePriority(form.priorities, i, i + 1); save(); renderPriorities(); });
      li.addEventListener("dragstart", (ev) => { dragFrom = i; ev.dataTransfer.effectAllowed = "move"; ev.dataTransfer.setData("text/plain", String(i)); li.classList.add("dragging"); });
      li.addEventListener("dragend", () => { dragFrom = null; li.classList.remove("dragging"); });
      li.addEventListener("dragover", (ev) => { ev.preventDefault(); ev.dataTransfer.dropEffect = "move"; });
      li.addEventListener("drop", (ev) => {
        ev.preventDefault();
        if (dragFrom !== null) form.priorities = movePriority(form.priorities, dragFrom, i);
        dragFrom = null; save(); renderPriorities();
      });
      li.append(check, text, up, down);
      el.list.append(li);
    });
  }

  function renderForm() {
    el.days.value = String(form.days);
    el.region.value = form.regionKey;
    el.customBox.hidden = form.regionKey !== "custom";
    el.latMin.value = String(form.custom.lat_min);
    el.latMax.value = String(form.custom.lat_max);
    el.step.value = String(form.custom.grid_step_deg);
    for (const b of el.mode) b.classList.toggle("active", b.dataset.mode === form.mode);
    el.catalog.checked = form.includeCatalog;
    el.height.value = String(form.heightM);
    renderSliders();
    renderPriorities();
  }

  function renderResults(response) {
    const rows = resultRows(response);
    el.head.replaceChildren();
    const cells = ["#", "Місце", "Бал", ...response.priorities.map((id) => FACTOR_LABELS[id] ?? id), "Сонце", "Зв'язок", "Станція DSN", "Статус"];
    for (const text of cells) el.head.append(Object.assign(document.createElement("th"), { scope: "col", textContent: text }));
    el.body.replaceChildren();
    for (const r of rows) {
      const tr = el.body.insertRow();
      tr.tabIndex = 0;
      tr.className = r.feasible ? "" : "infeasible";
      tr.title = "Показати це місце на карті Місяця й в оверлеї метрик";
      const put = (text) => { const td = tr.insertCell(); td.textContent = text; return td; };
      put(`${r.rank}${r.pareto ? " ★" : ""}`).title = r.pareto ? "Недомінована: жодна допустима точка не краща за всіма факторами" : "";
      put(r.place);
      const score = tr.insertCell();
      const bar = Object.assign(document.createElement("span"), { className: "bar" });
      bar.style.setProperty("--w", `${Math.round(r.scorePct)}%`);
      score.append(bar, Object.assign(document.createElement("b"), { textContent: ` ${r.scorePct.toFixed(1)}` }));
      for (const f of r.factors) put(percent(f.value)).title = f.label;
      put(r.sun);
      put(r.comm);
      put(r.station);
      const status = put(r.feasible ? "✓ допустима" : `✗ ${r.violations.join("; ")}`);
      status.className = r.feasible ? "ok" : "no";
      const open = () => {
        setState({ site: r.site.name ?? null, lat: r.site.lat, lon: r.site.lon });
        document.getElementById("moon-globe")?.scrollIntoView({ behavior: "smooth", block: "nearest" }); // до карти
      };
      tr.addEventListener("click", open);
      tr.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); open(); } });
    }
    el.table.hidden = rows.length === 0;
    el.advice.dataset.ready = rows.length ? "1" : "";
    el.note.textContent = gridNote(response.grid);
    el.note.classList.toggle("warn", response.grid.truncated);
    el.compare.textContent = describeComparison(response.comparison);
    el.compare.hidden = !response.comparison;
  }

  // ----- Порада ШІ (POST /api/advice): блок видно завжди; кнопка активна, коли сервер оголосив джерело "llm" у /api/meta -----
  function renderAdvice(a) {
    el.adviceOut.replaceChildren();
    const summary = Object.assign(document.createElement("p"), { className: "advice-summary", textContent: a.summary });
    const tips = document.createElement("ul");
    for (const tip of a.tips) {
      const li = document.createElement("li");
      li.textContent = tip.text;
      if (tip.related_metric) li.title = `Спирається на: ${tip.related_metric}`;
      tips.append(li);
    }
    const caveats = document.createElement("ul");
    caveats.className = "muted small";
    for (const c of a.caveats) caveats.append(Object.assign(document.createElement("li"), { textContent: c }));
    const meta = Object.assign(document.createElement("p"), {
      className: "muted small",
      textContent: `Модель ${a.model} · ${a.generated_utc}${a.verified ? " · числа перевірено за даними пошуку" : ""}`,
    });
    if (!a.verified) {
      el.adviceOut.append(Object.assign(document.createElement("p"), {
        className: "globe-warn", textContent: "Не всі числа у відповіді знайдено у даних пошуку — перевіряйте їх за таблицею.",
      }));
    }
    el.adviceOut.append(summary, tips, caveats, meta);
    el.adviceOut.hidden = false;
  }

  async function askAdvice() {
    if (!lastResponse) return;
    const body = {
      facts: buildAdviceFacts(lastResponse, form),
      language: "uk",
      audience: el.adviceAudience.value,
    };
    const question = el.adviceQuestion.value.trim();
    if (question) body.question = question.slice(0, 500);
    el.adviceAsk.disabled = true;
    el.adviceStatus.textContent = "Питаю ШІ…";
    el.adviceStatus.hidden = false;
    try {
      const res = await fetch("/api/advice", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      renderAdvice(data);
      el.adviceStatus.hidden = true;
    } catch (err) {
      el.adviceOut.hidden = true;
      el.adviceStatus.textContent = err.message;
    } finally {
      el.adviceAsk.disabled = false;
    }
  }

  async function run() {
    let body;
    try { body = buildSearchRequest(form, getState().datetime); } catch (err) { showStatus(err.message, true); return; }
    abort?.abort();
    abort = new AbortController();
    el.run.disabled = true;
    showStatus("Шукаю… (до ~25 с для великих областей)");
    try {
      const res = await fetch("/api/search", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: abort.signal });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      renderResults(data);
      publishHighlights(highlightPoints(data));
      lastResponse = data;
      el.adviceOut.hidden = true;
      el.adviceStatus.hidden = true;
      showStatus("");
    } catch (err) {
      if (err.name === "AbortError") return;
      el.table.hidden = true;
      el.compare.hidden = true;
      el.note.textContent = "";
      publishHighlights([]);
      showStatus(err.message, true);
    } finally {
      el.run.disabled = false;
    }
  }

  // події форми
  const numberOr = (input, fallback) => { const v = Number(input.value); return Number.isFinite(v) ? v : fallback; };
  el.days.addEventListener("change", () => { form.days = clamp(numberOr(el.days, form.days), 1, 120); save(); renderForm(); });
  el.region.addEventListener("change", () => { form.regionKey = el.region.value; save(); renderForm(); });
  for (const [input, key] of [[el.latMin, "lat_min"], [el.latMax, "lat_max"], [el.step, "grid_step_deg"]]) {
    input.addEventListener("change", () => { form.custom[key] = numberOr(input, form.custom[key]); save(); });
  }
  el.sun.addEventListener("input", () => { form.minSunHours = Number(el.sun.value); save(); renderSliders(); });
  el.comm.addEventListener("input", () => { form.minCommHours = Number(el.comm.value); save(); renderSliders(); });
  for (const b of el.mode) b.addEventListener("click", () => { form.mode = b.dataset.mode; save(); renderForm(); });
  el.catalog.addEventListener("change", () => { form.includeCatalog = el.catalog.checked; save(); });
  el.height.addEventListener("change", () => { form.heightM = clamp(numberOr(el.height, 0), 0, 1000); save(); renderForm(); });
  el.run.addEventListener("click", run);
  el.adviceAsk.addEventListener("click", askAdvice);

  renderForm();
  fetch("/api/meta").then((r) => r.json()).then((meta) => {
    available = new Set((meta.data_sources ?? []).map((s) => s.id));
    const advice = adviceState(meta); // блок порад видно завжди; без сервера — з поясненням
    for (const control of [el.adviceAsk, el.adviceQuestion, el.adviceAudience]) control.disabled = !advice.enabled;
    if (!advice.enabled) {
      el.adviceStatus.textContent = advice.note;
      el.adviceStatus.hidden = false;
    }
    renderPriorities();
  }).catch(() => { /* без /api/meta температура лишається вимкненою */ });
}
