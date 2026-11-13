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

// Параметри URL → частковий стан. Некоректні значення відкидаються.
export function parseUrlState(search) {
  const params = new URLSearchParams(search);
  const out = {};
  const datetime = params.get("datetime");
  if (datetime && Number.isFinite(Date.parse(datetime))) out.datetime = datetime;
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

function readInitial() {
  const fromUrl = typeof location === "undefined" ? {} : parseUrlState(location.search);
  // Посилання з параметрами — повний знімок стану: решта ключів беруть значення за замовчуванням,
  // а не з localStorage, інакше в іншій вкладці стан відрізнявся б.
  if (Object.keys(fromUrl).length) return { ...defaults(), ...fromUrl };
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
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch { /* ігноруємо */ }
  syncUrl();
  for (const fn of listeners) fn(getState());
}

export function subscribe(fn) {
  listeners.add(fn);
  fn(getState());
  return () => listeners.delete(fn);
}
