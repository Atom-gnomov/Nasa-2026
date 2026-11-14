// Політ «старт → Місяць» у 3D-виді системи (задача G9, пропозиція П-5): чисті функції без DOM і Three.js.
// Дані — `extras` з GET /api/scene?launch_site=… (ракета, траєкторія, модуль). Малює їх system_view.js.

// Запит сцени з польотом; null — майданчик не вибрано.
export function flightUrl(siteId, ms, lat = null, lon = null) {
  if (!siteId || !Number.isFinite(ms)) return null;
  const params = new URLSearchParams({
    datetime: new Date(ms).toISOString().slice(0, 19) + "Z", launch_site: siteId, markers: "0",
  });
  if (lat != null && lon != null) {
    params.set("lat", String(lat));
    params.set("lon", String(lon));
  }
  return `/api/scene?${params}`;
}

// extras → { rocket, trajectory, lander } (відсутні — null).
export function splitExtras(extras) {
  const pick = (kind) => (extras ?? []).find((e) => e.kind === kind) ?? null;
  return { rocket: pick("rocket"), trajectory: pick("trajectory"), lander: pick("lander") };
}

const dt = (iso) => (iso ? `${iso.slice(8, 10)}.${iso.slice(5, 7)} ${iso.slice(11, 16)}` : "—");

// Рядок для панелі «Стан системи».
export function flightFact(extras) {
  const { rocket, trajectory, lander } = splitExtras(extras);
  if (!trajectory) return "не вибрано майданчик старту";
  const days = trajectory.tof_days.toLocaleString("uk-UA", { maximumFractionDigits: 1 });
  const site = rocket ? rocket.name.split(" (")[0] : trajectory.launch_site_id;
  return `${site}: TLI ${dt(trajectory.departure_utc)} → прибуття ${dt(trajectory.arrival_utc)} UTC (${days} доби), ` +
    `Δv TLI ${Math.round(trajectory.dv_tli_m_s)} м/с, гальмування ${Math.round(trajectory.dv_loi_m_s)} м/с, ` +
    `вікон на добу: ${trajectory.windows_per_day}${lander ? "" : " · точку посадки не вибрано"}`;
}

// Чи треба перезапитати політ: інший майданчик, точка або час змістився більше ніж на stepMs.
export function needsReload(prev, next, stepMs = 6 * 3600000) {
  if (!prev) return Boolean(next.siteId);
  if (prev.siteId !== next.siteId || prev.lat !== next.lat || prev.lon !== next.lon) return true;
  return Boolean(next.siteId) && Math.abs(prev.ms - next.ms) > stepMs;
}
