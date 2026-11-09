// Модуль «Оверлей метрик»: запитує /api/metrics при зміні дати або місця.
import { subscribe } from "./state.js";

const root = document.getElementById("metrics-overlay");
const status = document.getElementById("overlay-status");

function render(values) {
  for (const el of root.querySelectorAll("[data-metric]")) {
    const v = values[el.dataset.metric];
    if (v === undefined || v === null) el.textContent = "—";
    else if (typeof v === "number") el.textContent = v.toFixed(2);
    else if (typeof v === "boolean") el.textContent = v ? "так" : "ні";
    else el.textContent = v;
  }
}

async function refresh({ lat, lon, datetime, site }) {
  if (lat === null || lon === null) {
    render({});
    status.textContent = "Виберіть місце на Місяці";
    return;
  }
  const params = new URLSearchParams({ lat, lon, datetime });
  try {
    const res = await fetch(`/api/metrics?${params}`);
    const data = await res.json();
    if (!res.ok) {
      render({ site: site ?? `${lat}, ${lon}` });
      status.textContent = data.detail || "Помилка розрахунку";
      return;
    }
    render({ site: site ?? `${lat}, ${lon}`, ...data });
    status.textContent = "";
  } catch {
    status.textContent = "Сервер недоступний";
  }
}

if (root) subscribe(refresh);
