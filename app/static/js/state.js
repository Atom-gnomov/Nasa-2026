// Спільний стан застосунку: дата, вибране місце, режим.
// Синхронізує вкладки через URL (?datetime=&lat=&lon=&site=) і localStorage.
// Інші модулі підписуються через subscribe() і змінюють стан через setState().

const STORAGE_KEY = "lse-state";
const listeners = new Set();

function readInitial() {
  let stored = {};
  try { stored = JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; } catch { /* приватний режим */ }
  const params = new URLSearchParams(location.search);
  const fromUrl = {};
  for (const key of ["datetime", "site"]) if (params.has(key)) fromUrl[key] = params.get(key);
  for (const key of ["lat", "lon"]) if (params.has(key)) fromUrl[key] = Number(params.get(key));
  return {
    datetime: new Date().toISOString().slice(0, 16) + "Z",
    site: null,
    lat: null,
    lon: null,
    ...stored,
    ...fromUrl,
  };
}

let state = readInitial();

export function getState() {
  return { ...state };
}

export function setState(patch) {
  state = { ...state, ...patch };
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch { /* ігноруємо */ }
  for (const fn of listeners) fn(getState());
}

export function subscribe(fn) {
  listeners.add(fn);
  fn(getState());
  return () => listeners.delete(fn);
}
