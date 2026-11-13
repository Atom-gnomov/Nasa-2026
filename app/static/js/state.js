// Спільний стан застосунку: дата, вибране місце, висота, режим, порівняння.
// Синхронізує вкладки через URL (?datetime=&lat=&lon=&site=&height=&mode=&compare=) і localStorage.
// URL оновлюється без перезавантаження (history.replaceState), тож адресою можна поділитися.
// Інші модулі підписуються через subscribe() і змінюють стан через setState().

const STORAGE_KEY = "lse-state";
export const MODES = ["earth-moon", "sun-moon-earth"];
const SITE_ID = /^[a-z0-9-]+$/; // id місця каталогу (схема Site у contracts/openapi.yaml)
const URL_KEYS = ["datetime", "site", "lat", "lon", "height", "mode", "compare"];
const listeners = new Set();

function defaults() {
  return {
    datetime: new Date().toISOString().slice(0, 16) + "Z",
    site: null,
    lat: null,
    lon: null,
    height_m: 0,
    mode: MODES[0],
    compare: [],
  };
}

const num = (raw, min, max) => {
  const v = raw === null || raw.trim() === "" ? NaN : Number(raw);
  return Number.isFinite(v) && v >= min && v <= max ? v : undefined;
};

// Дата й час ISO 8601 → UTC у форматі стану «YYYY-MM-DDTHH:mmZ»; секунди відкидаються.
// Без часу — відкидається; без зони — вважається UTC (як у календарі). Неіснуючі дати
// (30 лютого, 24:00) відкидаються, а не «перекочуються», як у Date.parse.
// Незакодований «+» зони в URL приходить як пробіл: «12:00:00 02:00» = «12:00:00+02:00».
const DATETIME = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(Z|[+\- ]\d{2}:?\d{2})?$/i;

export function normalizeDatetime(raw) {
  const m = DATETIME.exec(String(raw ?? "").trim());
  if (!m) return undefined;
  const [y, mo, d, h, mi, s] = m.slice(1, 7).map((v) => Number(v ?? 0));
  const zone = m[7] ?? "Z";
  const zoneH = /^z$/i.test(zone) ? 0 : Number(zone.slice(1, 3));
  const zoneM = /^z$/i.test(zone) ? 0 : Number(zone.slice(-2));
  if (h > 23 || mi > 59 || s > 59 || zoneH > 23 || zoneM > 59) return undefined;
  const wall = new Date(Date.UTC(y, mo - 1, d, h, mi, s));
  if (wall.getUTCFullYear() !== y || wall.getUTCMonth() !== mo - 1 || wall.getUTCDate() !== d) return undefined;
  const offsetMin = (zone[0] === "-" ? -1 : 1) * (zoneH * 60 + zoneM);
  const out = new Date(wall.getTime() - offsetMin * 60000).toISOString().slice(0, 16) + "Z";
  return /^\d{4}-/.test(out) ? out : undefined;
}

// Параметри URL → частковий стан. Некоректні значення відкидаються.
export function parseUrlState(search) {
  const params = new URLSearchParams(search);
  const out = {};
  const datetime = normalizeDatetime(params.get("datetime"));
  if (datetime) out.datetime = datetime;
  if (params.get("site")) out.site = params.get("site");
  const lat = num(params.get("lat"), -90, 90);
  const lon = num(params.get("lon"), -180, 360);
  if (lat !== undefined) out.lat = lat;
  if (lon !== undefined) out.lon = lon;
  const height = num(params.get("height"), 0, 1000); // межі параметра height в API
  if (height !== undefined) out.height_m = height;
  if (MODES.includes(params.get("mode"))) out.mode = params.get("mode");
  if (params.has("compare")) {
    const ids = params.getAll("compare").flatMap((v) => v.split(",")).map((v) => v.trim());
    out.compare = [...new Set(ids.filter((id) => SITE_ID.test(id)))];
  }
  return out;
}

// Стан → рядок запиту без «?». Чужі параметри з `search` зберігаються;
// значення за замовчуванням (висота 0, режим earth-moon, без порівняння) не пишуться.
export function serializeUrlState(state, search = "") {
  const params = new URLSearchParams(search);
  for (const key of URL_KEYS) params.delete(key);
  if (state.datetime) params.set("datetime", state.datetime);
  if (state.site) params.set("site", state.site);
  if (Number.isFinite(state.lat)) params.set("lat", String(state.lat));
  if (Number.isFinite(state.lon)) params.set("lon", String(state.lon));
  if (Number.isFinite(state.height_m) && state.height_m !== 0) params.set("height", String(state.height_m));
  if (MODES.includes(state.mode) && state.mode !== MODES[0]) params.set("mode", state.mode);
  if (Array.isArray(state.compare) && state.compare.length) params.set("compare", state.compare.join(","));
  return params.toString().replace(/%3A/gi, ":").replace(/%2C/gi, ",");
}

function save(snapshot) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot)); } catch { /* приватний режим */ }
}

function readInitial() {
  const fromUrl = typeof location === "undefined" ? {} : parseUrlState(location.search);
  // Посилання з параметрами — повний знімок стану: решта ключів беруть значення за замовчуванням,
  // а не з localStorage, інакше в іншій вкладці стан відрізнявся б. Знімок одразу зберігаємо,
  // щоб перехід через меню (адреса без параметрів) не повертав старий стан.
  if (Object.keys(fromUrl).length) {
    const snapshot = { ...defaults(), ...fromUrl };
    save(snapshot);
    return snapshot;
  }
  let stored = {};
  try { stored = JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; } catch { /* приватний режим */ }
  return { ...defaults(), ...stored };
}

function syncUrl() {
  if (typeof location === "undefined" || typeof history === "undefined") return;
  const query = serializeUrlState(state, location.search);
  const url = location.pathname + (query ? `?${query}` : "") + location.hash;
  if (url === location.pathname + location.search + location.hash) return;
  try { history.replaceState(history.state, "", url); } catch { /* браузер обмежує частоту replaceState */ }
}

let state = readInitial();
syncUrl();

export function getState() {
  return { ...state, compare: [...(state.compare || [])] };
}

export function setState(patch) {
  state = { ...state, ...patch };
  save(state);
  syncUrl();
  for (const fn of listeners) fn(getState());
}

export function subscribe(fn) {
  listeners.add(fn);
  fn(getState());
  return () => listeners.delete(fn);
}
