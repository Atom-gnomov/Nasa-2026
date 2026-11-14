// Політ «старт → Місяць» у 3D-виді системи (G9, П-5) і оптимальна точка старту (П-12): чисті функції без DOM і
// Three.js. Дані — `extras` з GET /api/scene?launch_site=… (ракета, траєкторія, модуль; для auto — траса площини
// відльоту й зведення вибору). Малює їх system_view.js.

// Значення списку «Політ із»: id майданчика або "auto:<criterion>:<scope>" (criterion — fuel | speed,
// scope — spaceports | any).
export const AUTO_OPTIONS = [
  { value: "auto:fuel:spaceports", label: "Оптимально: паливо, космодроми" },
  { value: "auto:speed:spaceports", label: "Оптимально: швидкість, космодроми" },
  { value: "auto:fuel:any", label: "Оптимально: паливо, будь-яка точка Землі" },
  { value: "auto:speed:any", label: "Оптимально: швидкість, будь-яка точка Землі" },
];

export function parseFlightValue(value) {
  const m = /^auto:(fuel|speed):(spaceports|any)$/.exec(value ?? "");
  if (m) return { siteId: "auto", criterion: m[1], scope: m[2] };
  return value ? { siteId: value, criterion: null, scope: null } : null;
}

// Запит сцени з польотом; null — політ вимкнено.
export function flightUrl(value, ms, lat = null, lon = null) {
  const choice = parseFlightValue(value);
  if (!choice || !Number.isFinite(ms)) return null;
  const params = new URLSearchParams({
    datetime: new Date(ms).toISOString().slice(0, 19) + "Z", launch_site: choice.siteId, markers: "0",
  });
  if (choice.criterion) {
    params.set("criterion", choice.criterion);
    params.set("launch_scope", choice.scope);
  }
  if (lat != null && lon != null) {
    params.set("lat", String(lat));
    params.set("lon", String(lon));
  }
  return `/api/scene?${params}`;
}

// extras → { rocket, trajectory, lander, groundTrack, choice } (відсутні — null).
export function splitExtras(extras) {
  const pick = (kind) => (extras ?? []).find((e) => e.kind === kind) ?? null;
  return {
    rocket: pick("rocket"), trajectory: pick("trajectory"), lander: pick("lander"),
    groundTrack: pick("ground_track"), choice: pick("launch_choice"),
  };
}

const dt = (iso) => (iso ? `${iso.slice(8, 10)}.${iso.slice(5, 7)} ${iso.slice(11, 16)}` : "—");
const num = (v, d = 1) => Number(v).toLocaleString("uk-UA", { maximumFractionDigits: d });
const shortName = (name) => String(name ?? "").split(" (")[0];
const CRITERION = { fuel: "паливо", speed: "швидкість" };
const SCOPE = { spaceports: "космодроми", any: "будь-яка точка Землі" };

// Рядок «Політ» для панелі «Стан системи».
export function flightFact(extras) {
  const { rocket, trajectory, lander } = splitExtras(extras);
  if (!trajectory) return "не вибрано майданчик старту";
  const site = rocket ? shortName(rocket.name) : trajectory.launch_site_id;
  return `${site}: TLI ${dt(trajectory.departure_utc)} → прибуття ${dt(trajectory.arrival_utc)} UTC ` +
    `(${num(trajectory.tof_days)} доби), Δv TLI ${Math.round(trajectory.dv_tli_m_s)} м/с, ` +
    `гальмування ${Math.round(trajectory.dv_loi_m_s)} м/с, вікон на добу: ${trajectory.windows_per_day}` +
    `${lander ? "" : " · точку посадки не вибрано"}`;
}

const optionText = (o) =>
  `${shortName(o.site.name)}${o.site.id === "any-point" ? ` (${num(o.site.lat)}°, ${num(o.site.lon)}°)` : ""}: ` +
  `${o.wait_h > 0.05 ? `очікування ${num(o.wait_h)} год, ` : "старт одразу, "}` +
  `Δv ${Math.round(o.dv_total_m_s)} м/с (нахил ${num(o.inclination_deg)}°, +${Math.round(o.dv_site_penalty_m_s)} м/с), ` +
  `прибуття ${dt(o.arrival_utc)} UTC`;

// Рядок «Звідки летіти»: найкращий варіант і до трьох альтернатив; порожньо — майданчик вибрано вручну.
export function choiceFact(extras, maxAlternatives = 3) {
  const { choice } = splitExtras(extras);
  if (!choice) return "—";
  const head = `Оптимально (${CRITERION[choice.criterion]}, ${SCOPE[choice.scope]}) — ${optionText(choice.best)}`;
  const alts = (choice.alternatives ?? []).slice(0, maxAlternatives).map(optionText);
  return alts.length ? `${head}. Далі: ${alts.join("; ")}` : `${head}. ${choice.best.note}`;
}

// Чи треба перезапитати політ: інший вибір, точка або час змістився більше ніж на stepMs.
export function needsReload(prev, next, stepMs = 6 * 3600000) {
  if (!prev) return Boolean(next.siteId);
  if (prev.siteId !== next.siteId || prev.lat !== next.lat || prev.lon !== next.lon) return true;
  return Boolean(next.siteId) && Math.abs(prev.ms - next.ms) > stepMs;
}
