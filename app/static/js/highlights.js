// Точки, які вкладка «Підбір» просить показати на глобусі тієї ж сторінки (F14).
// Лише обмін списком між модулями (search.js → globe_view.js); у спільний стан і URL він не потрапляє.
// Модуль — єдиний на сторінку, тож підписники бачать останній список навіть якщо підписалися пізніше.
const bus = new EventTarget();
let current = [];

/** Точка підсвічування: { lat, lon, rank (1 — найкраща), feasible }. */
export function publishHighlights(points) {
  current = Array.isArray(points) ? points.filter((p) => Number.isFinite(p?.lat) && Number.isFinite(p?.lon)) : [];
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
