// Результати вкладки «Підбір» для карти Місяця: обмін через sessionStorage.
// Структуровані метрики залишаються в API, тут лише координати маркерів.
const STORAGE_KEY = "lse-search-highlights";
const bus = new EventTarget();
function readSaved() {
  try {
    const list = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(list) ? list.filter((p) => Number.isFinite(p?.lat) && Number.isFinite(p?.lon)).slice(0, 300) : [];
  } catch { return []; }
}
let current = readSaved();

/** Точка підсвічування: { lat, lon, rank (1 — найкраща), feasible }. */
export function publishHighlights(points) {
  current = Array.isArray(points) ? points.filter((p) => Number.isFinite(p?.lat) && Number.isFinite(p?.lon)).slice(0, 300) : [];
  try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(current)); } catch { /* приватний режим */ }
  bus.dispatchEvent(new Event("change"));
}

export const getHighlights = () => current.slice();

/** Підписка на зміни; обробник викликається одразу з поточним списком. Повертає функцію відписки. */
export function subscribeHighlights(fn) {
  const handler = () => fn(getHighlights());
  bus.addEventListener("change", handler);
  handler();
  return () => bus.removeEventListener("change", handler);
}
