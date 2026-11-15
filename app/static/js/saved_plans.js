// Збереження й відкриття планів місій (F30, П-14): знімок усіх виборів майстра (місія, мета, політ, лідер плану, вимоги
// підбору, дата й точка) у localStorage, копія для порівняння варіантів, експорт/імпорт файлом. Чисті функції — без DOM,
// сховище береться з globalThis.localStorage (у тестах підміняється). Файл не містить нічого, крім виборів.
import { t, onLangChange } from "./i18n.js";
import { getState, setState } from "./state.js";
import { STORAGE_KEY as SEARCH_KEY } from "./search.js";
import { LAUNCH_KEY } from "./pipeline.js";
import { MISSION_KEY, PLAN_LEAD_KEY } from "./selection.js";
import { GOALS, PLAN_KEY, loadPlan } from "./mission_plan.js";

export const PLANS_KEY = "lse-saved-plans";
export const FILE_VERSION = 1;
export const MAX_PLANS = 20;
const MAX_SNAPSHOT_CHARS = 60000; // один план — до ~60 КБ тексту; більше — це не вибори майстра
// Що входить у знімок: ім'я в знімку → ключ localStorage (JSON). Дата й точка — зі спільного стану окремо.
export const STORES = { mission: MISSION_KEY, plan: PLAN_KEY, launch: LAUNCH_KEY, lead: PLAN_LEAD_KEY, search: SEARCH_KEY };
const STATE_KEYS = ["datetime", "site", "lat", "lon"];

const storage = () => globalThis.localStorage;
const readKey = (key) => { try { return JSON.parse(storage()?.getItem(key) ?? "null"); } catch { return null; } };
const writeKey = (key, value) => {
  try {
    if (value === null || value === undefined) storage()?.removeItem(key);
    else storage()?.setItem(key, JSON.stringify(value));
  } catch { /* приватний режим */ }
};
const isObject = (x) => x !== null && typeof x === "object" && !Array.isArray(x);

// Знімок поточних виборів із спільних сховищ.
export function snapshotNow(state = getState()) {
  const data = Object.fromEntries(Object.entries(STORES).map(([name, key]) => [name, readKey(key)]));
  data.state = Object.fromEntries(STATE_KEYS.map((k) => [k, state[k] ?? null]));
  return data;
}

// Перевірка знімка (з файлу чи сховища): лише відомі розділи, об'єкти або null, розмір обмежено.
export function normalizeSnapshot(raw) {
  if (!isObject(raw)) return null;
  const out = {};
  for (const name of [...Object.keys(STORES), "state"]) {
    const v = raw[name];
    out[name] = isObject(v) ? v : null;
  }
  if (out.state) out.state = Object.fromEntries(STATE_KEYS.map((k) => [k, ["string", "number"].includes(typeof out.state[k]) ? out.state[k] : null]));
  if (JSON.stringify(out).length > MAX_SNAPSHOT_CHARS) return null;
  return out;
}

const cleanName = (name) => String(name ?? "").trim().slice(0, 80) || t("Без назви");

export function normalizeEntry(raw) {
  if (!isObject(raw)) return null;
  const data = normalizeSnapshot(raw.data);
  if (!data || typeof raw.id !== "string" || !/^[\w-]{1,40}$/.test(raw.id)) return null;
  const savedAt = typeof raw.savedAt === "string" && !Number.isNaN(Date.parse(raw.savedAt)) ? raw.savedAt : new Date(0).toISOString();
  return { id: raw.id, name: cleanName(raw.name), savedAt, data };
}

export function loadPlans() {
  const list = readKey(PLANS_KEY);
  return Array.isArray(list) ? list.map(normalizeEntry).filter(Boolean).slice(0, MAX_PLANS) : [];
}
export const storePlans = (plans) => writeKey(PLANS_KEY, plans.slice(0, MAX_PLANS));

let counter = 0;
const newId = () => `p${Date.now().toString(36)}${(counter++).toString(36)}`;

// Зберегти поточні вибори під ім'ям; план із таким самим ім'ям оновлюється. Повертає { plans, entry, replaced } або null, коли місця немає.
export function savePlanNow(plans, name, data, now = new Date()) {
  const label = cleanName(name);
  const entry = { id: newId(), name: label, savedAt: now.toISOString(), data: normalizeSnapshot(data) };
  const i = plans.findIndex((p) => p.name === label);
  if (i >= 0) return { plans: plans.map((p, k) => (k === i ? { ...entry, id: p.id } : p)), entry: { ...entry, id: plans[i].id }, replaced: true };
  if (plans.length >= MAX_PLANS) return null;
  return { plans: [entry, ...plans], entry, replaced: false };
}

// Копія для порівняння варіантів: «Назва (копія)», «Назва (копія 2)» … — ім'я не збігається з наявними.
export function duplicatePlan(plans, id, now = new Date()) {
  const src = plans.find((p) => p.id === id);
  if (!src || plans.length >= MAX_PLANS) return null;
  const base = src.name.replace(/ \(копія(?: \d+)?\)$/, "");
  let name = `${base} (копія)`;
  for (let n = 2; plans.some((p) => p.name === name); n += 1) name = `${base} (копія ${n})`;
  const entry = { id: newId(), name, savedAt: now.toISOString(), data: structuredClone(src.data) };
  return { plans: [entry, ...plans], entry };
}

export const removePlan = (plans, id) => plans.filter((p) => p.id !== id);

// Підпис плану в списку: тип, тривалість, мета, точка — з того, що є у знімку.
export function describePlan(entry) {
  const d = entry.data;
  const parts = [];
  if (d.mission) parts.push(d.mission.crewed ? t("пілотована") : t("безпілотна"));
  if (d.mission?.crewed && Number.isFinite(Number(d.mission.days))) parts.push(`${Number(d.mission.days)} ${t("діб")}`);
  const goal = GOALS.find((g) => g.id === d.plan?.goal);
  if (goal?.id) parts.push(t(goal.label));
  if (Number.isFinite(d.state?.lat) && Number.isFinite(d.state?.lon)) parts.push(`${d.state.lat.toFixed(1)}°, ${d.state.lon.toFixed(1)}°`);
  if (typeof d.state?.datetime === "string") parts.push(d.state.datetime.slice(0, 10));
  return parts.join(" · ");
}

// Застосувати план: записати розділи у сховища (відсутній — прибрати) і дату з точкою у спільний стан.
export function applySnapshot(data) {
  const snap = normalizeSnapshot(data);
  if (!snap) return false;
  for (const [name, key] of Object.entries(STORES)) writeKey(key, snap[name]);
  if (snap.state) setState({ datetime: snap.state.datetime ?? getState().datetime, site: snap.state.site, lat: snap.state.lat, lon: snap.state.lon });
  return true;
}

// Файл обміну: версія й плани; ім'я файлу — з назви.
export function exportFile(plans) {
  return JSON.stringify({ app: "lunar-mission-builder", version: FILE_VERSION, plans }, null, 2);
}

// Розбір файлу: { plans } або { error }; кожен план перевіряється, зайве відкидається, id призначаються нові.
export function parseImport(text) {
  let raw;
  try { raw = JSON.parse(text); } catch { return { error: t("Файл не схожий на збережені плани (не JSON).") }; }
  if (!isObject(raw) || raw.version !== FILE_VERSION || !Array.isArray(raw.plans)) return { error: t("Файл не схожий на збережені плани місій.") };
  const plans = raw.plans.map((p) => normalizeEntry({ ...p, id: isObject(p) ? newId() : "" })).filter(Boolean);
  if (!plans.length) return { error: t("У файлі немає жодного дійсного плану.") };
  return { plans };
}

// Додає імпортовані плани до наявних: однойменні отримують суфікс «(імпорт)», вміст — до ліміту.
export function mergeImported(plans, imported) {
  const out = [...plans];
  let skipped = 0;
  for (const p of imported) {
    if (out.length >= MAX_PLANS) { skipped += 1; continue; }
    let name = p.name;
    for (let n = 1; out.some((x) => x.name === name); n += 1) name = `${p.name} (імпорт${n > 1 ? ` ${n}` : ""})`;
    out.unshift({ ...p, name });
  }
  return { plans: out, skipped };
}

// ---------- DOM ----------
function init() {
  const box = document.getElementById("mp-plans");
  if (!box) return;
  const $ = (sel) => box.querySelector(sel);
  const el = (tag, props = {}, ...kids) => { const n = Object.assign(document.createElement(tag), props); n.append(...kids); return n; };
  let plans = loadPlans();
  const say = (text) => { $(".mp-plans-note").textContent = text; };

  function render() {
    $(".mp-plans-empty").hidden = plans.length > 0;
    $(".mp-plans-list").replaceChildren(...plans.map((p) => {
      const open = el("button", { type: "button", textContent: t("Відкрити") });
      open.addEventListener("click", () => { if (applySnapshot(p.data)) location.reload(); });
      const copy = el("button", { type: "button", textContent: t("Копія"), title: t("Копія для порівняння варіантів") });
      copy.addEventListener("click", () => {
        const res = duplicatePlan(plans, p.id);
        if (!res) { say(t("Досягнуто ліміту планів: видаліть зайві.")); return; }
        plans = res.plans; storePlans(plans); render(); say(t("Створено копію: {name}.", { name: res.entry.name }));
      });
      const del = el("button", { type: "button", textContent: "×", title: t("Видалити план"), "aria-label": t("Видалити план") });
      del.addEventListener("click", () => { plans = removePlan(plans, p.id); storePlans(plans); render(); });
      return el("li", {}, el("strong", { textContent: p.name }), el("span", { className: "muted small", textContent: describePlan(p) }), el("span", { className: "mp-plan-btns" }, open, copy, del));
    }));
  }

  $(".mp-plans-save").addEventListener("click", () => {
    const res = savePlanNow(plans, loadPlan().name, snapshotNow());
    if (!res) { say(t("Досягнуто ліміту планів: видаліть зайві.")); return; }
    plans = res.plans; storePlans(plans); render();
    say(t(res.replaced ? "План «{name}» оновлено." : "План «{name}» збережено.", { name: res.entry.name }));
  });
  $(".mp-plans-export").addEventListener("click", () => {
    if (!plans.length) { say(t("Немає планів для експорту.")); return; }
    const a = el("a", { href: URL.createObjectURL(new Blob([exportFile(plans)], { type: "application/json;charset=utf-8" })), download: "mission-plans.json" });
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  });
  const file = $(".mp-plans-file");
  $(".mp-plans-import").addEventListener("click", () => file.click());
  file.addEventListener("change", async () => {
    const f = file.files?.[0];
    file.value = "";
    if (!f) return;
    const res = parseImport(await f.text());
    if (res.error) { say(res.error); return; }
    const merged = mergeImported(plans, res.plans);
    plans = merged.plans; storePlans(plans); render();
    say(t("Імпортовано планів: {n}.", { n: res.plans.length - merged.skipped }) + (merged.skipped ? ` ${t("Не вмістилось: {n}.", { n: merged.skipped })}` : ""));
  });
  window.addEventListener("storage", (e) => { if (e.key === PLANS_KEY) { plans = loadPlans(); render(); } });
  onLangChange(render);
  render();
}

if (typeof document !== "undefined") init();
