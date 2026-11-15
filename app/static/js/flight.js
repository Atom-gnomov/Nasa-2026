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
export function flightUrl(value, ms, lat = null, lon = null, route = "direct") {
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
  params.set("anchor", "arrival"); // календар — дата посадки: старт обчислюється назад від неї
  if (route === "low_energy") params.set("trajectory", "low_energy"); // G17: економний маршрут — інша траса й тривалість
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
  if ((prev.route ?? "direct") !== (next.route ?? "direct")) return true; // інший маршрут — нова траса
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

// ---- Політ із посадкою: інтерполяція стану системи та фаза спуску ---------------------------------------------
// Місяць за 5 діб проходить десятки градусів, тож стан системи беремо з відліків (щогодини) й інтерполюємо:
// без запитів у кожному кадрі й без ривків. samples — [{ ms, state }] за зростанням ms; state — відповідь /api/system.
const lerpVec = (a, b, f) => a.map((v, i) => v + (b[i] - v) * f);
const lerpMat = (a, b, f) => a.map((row, i) => lerpVec(row, b[i], f));

export function interpSystem(samples, ms) {
  if (!samples?.length) return null;
  if (ms <= samples[0].ms) return samples[0].state;
  const last = samples[samples.length - 1];
  if (ms >= last.ms) return last.state;
  let lo = 0, hi = samples.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (samples[mid].ms <= ms) lo = mid; else hi = mid;
  }
  const f = (ms - samples[lo].ms) / (samples[hi].ms - samples[lo].ms);
  const a = samples[lo].state, b = samples[hi].state;
  // datetime і орієнтація Землі лишаються з попереднього відліку: обертання Землі система екстраполює сама
  return {
    ...a,
    moon_km: lerpVec(a.moon_km, b.moon_km, f),
    sun_km: lerpVec(a.sun_km, b.sun_km, f),
    moon_orientation: lerpMat(a.moon_orientation, b.moon_orientation, f),
  };
}

// Крок відліків залежить від тривалості: щогодини, але не більше maxSamples відліків (економний маршрут ≈ 105 діб — раз на ~15 год;
// Місяць і Сонце між відліками інтерполюються).
export function sampleStepMs(totalS, maxSamples = 168) {
  const hour = 3600000;
  return Math.max(hour, Math.ceil((Math.max(0, Number(totalS) || 0) * 1000) / maxSamples / hour) * hour);
}

// Відліки часу для польоту: від відльоту до прибуття щогодини (+ кінець).
export function sampleTimes(departureMs, totalS, stepMs = 3600000) {
  const end = departureMs + totalS * 1000;
  const out = [];
  for (let t = departureMs; t < end; t += stepMs) out.push(t);
  out.push(end);
  return out;
}

// Біля Місяця схематичний масштаб роздуває його в 6 разів, а дуга закінчується в центрі: ракета пролітала б крізь кулю.
// Відстань s (у одиницях сцени) від центру Місяця стискаємо так, щоб ракета підходила до висоти орбіти (orbitK·R),
// а не до центру; далі від k·R (s0) відстань не змінюється. Неперервно на s = s0.
export function remapNearMoon(s, rMoon, k = 7, orbitK = 1.35) {
  const s0 = rMoon * k, r1 = rMoon * orbitK;
  return s >= s0 ? s : r1 + (s0 - r1) * (Math.max(s, 0) / s0);
}

export const DESCENT_REAL_S = 7; // тривалість анімації спуску, с реального часу
export const ORBIT_ALT_KM = 100; // схематична висота початку спуску

// Стан спуску за прогресом p ∈ [0, 1]: e — частка пройденого вниз (гальмування до нуля), висота й швидкість (схематично).
export function descentState(p) {
  const x = Math.min(Math.max(Number(p) || 0, 0), 1);
  const e = 1 - (1 - x) ** 2; // м'яке торкання: швидкість падіння → 0
  return { p: x, e, altKm: ORBIT_ALT_KM * (1 - e), speedKmS: 1.63 * Math.sqrt(Math.max(0, 1 - e)), landed: x >= 1 };
}

export function descentRows(p, site = null) {
  const d = descentState(p);
  if (d.landed) {
    return [["Фаза", "Посадка виконана"], ["Висота над поверхнею", "0 м"], ["Швидкість", "0,00 км/с"],
      ...(site ? [["Точка посадки", site]] : [])];
  }
  return [
    ["Фаза", "Спуск і посадка"],
    ["Висота над поверхнею (схем.)", `${d.altKm.toFixed(1)} км`],
    ["Швидкість (схем.)", `${d.speedKmS.toFixed(2).replace(".", ",")} км/с`],
    ["Пройдено", `${Math.round(d.p * 100)} %`],
  ];
}

// ---- Розгін TLI з урахуванням маси завантаження (G16) -----------------------------------------------------------
export const BURN_REAL_S = 5; // тривалість анімації розгону, с реального часу (сам розгін триває хвилини)
const g1 = (v) => Number(v).toLocaleString("uk-UA", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// Чи дані розгону придатні для анімації (відповідь /api/mission, flight_phases.tli).
export const validBurn = (b) => Boolean(b && Number.isFinite(b.duration_s) && b.duration_s > 0 && Number.isFinite(b.accel_start_g)
  && Number.isFinite(b.mass_start_kg) && Number.isFinite(b.mass_end_kg));

// Стан розгону на частці p ∈ [0, 1]: час, залишок, маса й прискорення (лінійно між початком і кінцем).
export function burnStateAt(burn, p) {
  const f = Math.min(1, Math.max(0, Number(p) || 0));
  return {
    p: f, elapsedS: burn.duration_s * f, remainingS: burn.duration_s * (1 - f),
    massKg: burn.mass_start_kg + (burn.mass_end_kg - burn.mass_start_kg) * f,
    accelG: burn.accel_start_g + (burn.accel_end_g - burn.accel_start_g) * f, done: f >= 1,
  };
}

// Рядки телеметрії під час розгону.
export function burnRows(burn, p) {
  const st = burnStateAt(burn, p);
  const rows = [
    ["Фаза", "Розгін до Місяця (TLI)"],
    ["Час розгону", fmtDuration(st.elapsedS)],
    ["Залишилось розгону", fmtDuration(st.remainingS)],
    ["Прискорення", `${g1(st.accelG)} g`],
    ["Маса ракети", `${Math.round(st.massKg).toLocaleString("uk-UA")} кг`],
    ["Заповненість ракети", `${Math.round(burn.utilization * 100)} %`],
  ];
  if (burn.overloaded) rows.push(["Увага", "вантаж більший за місткість ракети"]);
  return rows;
}

// Короткий підсумок розгону для телеметрії перельоту.
export function burnSummaryRows(burn) {
  if (!validBurn(burn)) return [];
  return [["Розгін TLI", `${fmtDuration(burn.duration_s)}, ${g1(burn.accel_start_g)} → ${g1(burn.accel_end_g)} g`],
    ["Заповненість ракети", `${Math.round(burn.utilization * 100)} %${burn.overloaded ? " ⚠" : ""}`]];
}

// Відстань камери (одиниці сцени), щоб траса радіуса reach вмістилась у видиму смугу між бічними віджетами: із запасом на поле
// зору й на те, що траса йде в один бік. 0 — траси немає.
export function fitDistance(reach, factor = 3.4) {
  return Number.isFinite(reach) && reach > 0 ? reach * factor : 0;
}

// Швидкість симуляції (с польоту на 1 с реального часу) за тривалістю перельоту: щоб переліт займав ≈ 20 с реальних.
export const SPEED_CHOICES = [3600, 14400, 43200, 86400, 259200];
export function defaultSimSpeed(tofS) {
  const want = Math.max(0, Number(tofS) || 0) / 20;
  return SPEED_CHOICES.find((v) => v >= want) ?? SPEED_CHOICES[SPEED_CHOICES.length - 1];
}

// Час сцени під час розгону й плавний набір швидкості (G12+): розгін закінчується в момент відльоту (TLI), тож сцена
// «доживає» до нього, а не стоїть на місці; після розгону швидкість часу наростає плавно, а не стрибком.
export const BURN_LEAD_S = 3600; // скільки секунд часу сцени проходить за розгін (Земля повертається приблизно на 15°)
export const TIME_RAMP_S = 4; // за скільки секунд реального часу швидкість часу доростає до вибраної

/** Момент часу сцени під час розгону на частці p ∈ [0, 1]: до відльоту t0 лишається (1 − p)·BURN_LEAD_S. */
export const burnSceneMs = (t0Ms, p) => t0Ms - BURN_LEAD_S * 1000 * (1 - Math.min(1, Math.max(0, p)));

/** Швидкість часу сцени (с польоту на 1 с реального) на початку переліту — та, з якою йшов розгін. */
export const burnTimeRate = () => BURN_LEAD_S / BURN_REAL_S;

/** Швидкість часу через realS секунд переліту: плавно (smoothstep) від `from` до `target` за rampS секунд. */
export function rampedSpeed(from, target, realS, rampS = TIME_RAMP_S) {
  const k = Math.min(1, Math.max(0, realS / rampS));
  return from + (target - from) * k * k * (3 - 2 * k);
}

// ---------- Часова симуляція й симуляція польоту ----------
// Поки йде політ, час сцени веде ракета, тож часову симуляцію (▶) ставимо на паузу, а після польоту (посадка чи «Стоп»)
// вмикаємо знову. Стан: { playing — час іде; resume — час треба ввімкнути після польоту; flight — політ іде }.
export const timeInitial = () => ({ playing: false, resume: false, flight: false });

/** Початок польоту: якщо час ішов (або його вже просили ввімкнути) — запам'ятовуємо й зупиняємо. */
export function timeOnFlightStart(st) {
  return { playing: false, resume: st.resume || st.playing, flight: true };
}

/** Кнопка ▶/⏸ часу: під час польоту лише запам'ятовує бажання (час ввімкнеться після польоту), інакше перемикає час. */
export function timeOnPlayPress(st) {
  if (st.flight) return { ...st, resume: !st.resume };
  return { ...st, playing: !st.playing, resume: false };
}

/** Кінець польоту (посадка або «Стоп»): вмикаємо час, якщо він мав іти. */
export function timeOnFlightEnd(st) {
  return { playing: st.playing || st.resume, resume: false, flight: false };
}
