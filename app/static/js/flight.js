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

// ---- Симуляція польоту (G12): положення, швидкість, час і затримка зв'язку вздовж дуги з `trajectory` ------------
export const LIGHT_KM_S = 299792.458;
export const SIM_SPEEDS = [
  { value: 3600, label: "1 год/с" }, { value: 14400, label: "4 год/с" }, { value: 43200, label: "12 год/с" },
];

// Тривалість у секундах → «3 д 4 год», «5 год 12 хв», «42 с».
export function fmtDuration(seconds) {
  const s = Math.max(0, Math.round(Number(seconds) || 0));
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  if (d) return `${d} д ${h} год`;
  if (h) return `${h} год ${m} хв`;
  return m ? `${m} хв ${s % 60} с` : `${s} с`;
}

const lerp = (a, b, f) => a + (b - a) * f;
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);

// Номер відрізка дуги, що містить час t (двійковий пошук за times_s) і частка всередині нього.
function segment(times, t) {
  if (t <= times[0]) return [0, 0];
  if (t >= times[times.length - 1]) return [times.length - 2, 1];
  let lo = 0, hi = times.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (times[mid] <= t) lo = mid; else hi = mid;
  }
  return [lo, (t - times[lo]) / (times[hi] - times[lo])];
}

// Стан ракети через `elapsedS` секунд після відльоту: положення (км), напрям і швидкість (км/с), час, залишок,
// відстані до Землі й до точки прибуття, затримка радіосигналу до Землі (с). null — немає даних для анімації.
export function stateAt(trajectory, elapsedS) {
  const { points_km: pts, times_s: times, speeds_km_s: speeds } = trajectory ?? {};
  if (!pts || !times || !speeds || pts.length < 2 || times.length !== pts.length) return null;
  const total = times[times.length - 1];
  const t = Math.min(Math.max(Number(elapsedS) || 0, 0), total);
  const [i, f] = segment(times, t);
  const a = pts[i], b = pts[i + 1];
  const pos = [lerp(a[0], b[0], f), lerp(a[1], b[1], f), lerp(a[2], b[2], f)];
  const len = dist(a, b) || 1;
  const dir = [(b[0] - a[0]) / len, (b[1] - a[1]) / len, (b[2] - a[2]) / len];
  const distEarth = Math.hypot(...pos);
  return {
    elapsedS: t, remainingS: total - t, totalS: total, progress: total > 0 ? t / total : 1, done: t >= total,
    pos, dir, speedKmS: lerp(speeds[i], speeds[i + 1], f),
    distEarthKm: distEarth, distTargetKm: dist(pos, trajectory.moon_at_arrival_km ?? pts[pts.length - 1]),
    delayS: distEarth / LIGHT_KM_S,
  };
}

const km = (v) => `${Math.round(v).toLocaleString("uk-UA")} км`;

// Рядки панелі «Телеметрія»: [назва, значення].
export function telemetryRows(st) {
  if (!st) return [];
  return [
    ["Час польоту", fmtDuration(st.elapsedS)],
    ["Залишилось", st.done ? "прибуття" : fmtDuration(st.remainingS)],
    ["Пройдено", `${Math.round(st.progress * 100)} %`],
    ["Швидкість", `${st.speedKmS.toLocaleString("uk-UA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} км/с`],
    ["Відстань до Землі", km(st.distEarthKm)],
    ["До точки прибуття", km(st.distTargetKm)],
    ["Затримка зв'язку із Землею", `${st.delayS.toLocaleString("uk-UA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} с (в один бік)`],
  ];
}
