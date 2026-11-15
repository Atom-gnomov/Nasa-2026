// Єдиний конвеєр вибору між вкладками (F20): вимоги до місця посадки живуть у «Підборі», вибір польоту (майданчик,
// траєкторія, ракета) — один для «Системи», «Плану місії» й «Вікна запуску». Те, що вибрано раніше, не вводимо знову.
// Чисті функції — без DOM; сховище — localStorage (недоступне — не ламаємо сторінки).
import { REGIONS, STORAGE_KEY as SEARCH_KEY, buildSearchRequest, hoursText } from "./search.js";

export const LAUNCH_KEY = "lse-launch";
const TRAJECTORIES = ["any", "direct", "low_energy"];
const AUTO = /^auto:(fuel|speed):(spaceports|any)$/;

const read = (key) => { try { return JSON.parse(globalThis.localStorage?.getItem(key) ?? "null"); } catch { return null; } };
const write = (key, value) => { try { globalThis.localStorage?.setItem(key, JSON.stringify(value)); } catch { /* не критично */ } };

// ---------- Політ: майданчик, траєкторія, ракета ----------
export const DEFAULT_LAUNCH = { site: "", trajectory: "any", vehicle: "any", departure: "", arrival: "" };
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

// site: "" — не вибрано; id майданчика; або "auto:<fuel|speed>:<spaceports|any>" (оптимум, як у «Системі»).
export function normalizeLaunch(raw) {
  const out = { ...DEFAULT_LAUNCH };
  if (!raw || typeof raw !== "object") return out;
  if (typeof raw.site === "string" && (/^[a-z0-9-]+$/.test(raw.site) || AUTO.test(raw.site))) out.site = raw.site;
  if (TRAJECTORIES.includes(raw.trajectory)) out.trajectory = raw.trajectory;
  if (typeof raw.vehicle === "string" && /^[a-z0-9._-]+$/i.test(raw.vehicle)) out.vehicle = raw.vehicle;
  // «Вікно запуску» віддає далі найкращу дату старту (YYYY-MM-DD) і прибуття (ISO) — їх підхоплюють «План місії», «Мій план»
  if (typeof raw.departure === "string" && ISO_DATE.test(raw.departure)) out.departure = raw.departure;
  if (typeof raw.arrival === "string" && /^\d{4}-\d{2}-\d{2}T/.test(raw.arrival)) out.arrival = raw.arrival.slice(0, 25);
  return out;
}

export const loadLaunch = () => normalizeLaunch(read(LAUNCH_KEY));
export function saveLaunch(patch) {
  const next = normalizeLaunch({ ...loadLaunch(), ...patch });
  write(LAUNCH_KEY, next);
  return next;
}

export const isAuto = (site) => AUTO.test(site ?? "");
// Пріоритети «Вікна запуску» (light/fuel/comms/windows) за пріоритетами «Підбору»: Енергія → світло, Зв'язок → зв'язок, далі
// паливо й вікна на добу. Перший у списку — найважливіший (ваги ROC за порядком).
export function windowPriorities(searchForm) {
  const map = { energy: "light", comms: "comms" };
  const out = [];
  for (const p of searchForm?.priorities ?? []) if (p.on && map[p.id] && !out.includes(map[p.id])) out.push(map[p.id]);
  for (const f of ["light", "fuel", "comms", "windows"]) if (!out.includes(f)) out.push(f);
  return out;
}

// Скільки діб після прибуття оцінювати світло й зв'язок: тривалість перебування з «Місії» (пілотована), інакше типово 7.
export function stayDays(mission) {
  const d = Number(mission?.days);
  return mission?.crewed && Number.isFinite(d) && d >= 1 ? Math.min(60, Math.round(d)) : 7;
}

// Конкретний майданчик (не «оптимально»); інакше null.
export const plainSite = (site) => (site && !isAuto(site) ? site : null);

// Який майданчик показувати вкладкам: явний вибір користувача, інакше лідер плану (lead — з selection.js).
export function effectiveSite(launch, lead) {
  return launch.site || lead?.siteId || "";
}

// Траєкторія для вкладок: явна, інакше траєкторія лідера плану, інакше «пряма».
export function effectiveTrajectory(launch, lead) {
  if (launch.trajectory !== "any") return launch.trajectory;
  return lead?.trajectory === "low_energy" ? "low_energy" : "direct";
}

// ---------- Вимоги до місця посадки: беремо з «Підбору» ----------
export const loadSearchForm = () => read(SEARCH_KEY);

const regionLabel = (form) => {
  const key = form.regionKey in REGIONS ? form.regionKey : "pole";
  if (key !== "custom") return REGIONS[key].label;
  const c = form.custom ?? {};
  return `широта ${c.lat_min}…${c.lat_max}°, крок ${c.grid_step_deg}°`;
};

// Короткий опис вимог із «Підбору» для «Плану місії»: [[назва, значення], …] (без полів, де вимоги немає).
export function requirementsSummary(form) {
  if (!form || typeof form !== "object") return [];
  const rows = [["Область", regionLabel(form)], ["Період", `${form.days ?? 30} діб`]];
  if (form.minSunHours > 0) rows.push(["Мін. годин Сонця", hoursText(form.minSunHours)]);
  if (form.minCommHours > 0) rows.push(["Мін. годин зв'язку", hoursText(form.minCommHours)]);
  if (form.maxSlopeDeg > 0) rows.push(["Макс. нахил", `${form.maxSlopeDeg}°`]);
  if (form.minEarthPct > 0) rows.push(["Мін. частка Землі (м'яка)", `${form.minEarthPct} %`]);
  if (form.minSunPct > 0) rows.push(["Мін. частка Сонця (м'яка)", `${form.minSunPct} %`]);
  const on = (form.priorities ?? []).filter((p) => p.on).map((p) => p.id);
  if (on.length) rows.push(["Пріоритети", on.join(" › ")]);
  return rows;
}

// Вимоги «Підбору» → частина тіла POST /api/plan (регіон, сітка, період, пороги, пріоритети). Помилка — якщо не можна
// побудувати запит (немає факторів чи дати).
export function planRequirements(searchForm, datetime) {
  const { limit, ...body } = buildSearchRequest(searchForm, datetime); // limit у плані свій
  return body;
}
