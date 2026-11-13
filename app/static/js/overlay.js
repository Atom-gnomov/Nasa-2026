// Модуль «Оверлей метрик» (М11): усі вимірювання системи для вибраної точки й дати.
// Джерела — незалежні ендпоінти, кожен розділ заповнюється, щойно приходить свій запит:
//   /api/metrics     — Сонце, Земля, DSN, енергія в цей момент (DE440 + горизонт LOLA);
//   /api/elevation   — висота, нахил і експозиція схилу (найдетальніший DEM LOLA);
//   /api/horizon     — маска горизонту, частка відкритого неба, оцінка дози ГКП;
//   /api/temperature — температура LRO Diviner (на дату, за добу, полярний PRP, лід);
//   /api/timeline    — підсумки за місячну добу від дати (години Сонця/зв'язку, найдовша ніч, енергія).
import { subscribe } from "./state.js";

const root = document.getElementById("metrics-overlay");
const status = document.getElementById("overlay-status");
const SYNODIC_MONTH_H = 29.530589 * 24;

const set = (key, text, cls = "") => {
  const el = root.querySelector(`[data-m="${key}"]`);
  if (!el) return;
  el.textContent = text ?? "—";
  el.className = cls;
};
const deg = (v, d = 2) => (v == null ? "—" : `${v.toFixed(d)}°`);
const pct = (v) => (v == null ? "—" : `${Math.round(v * 100)} %`);
const km = (v) => (v == null ? "—" : `${Math.round(v).toLocaleString("uk-UA")} км`);
const kelvin = (v) => (v == null ? "—" : `${Math.round(v)} K (${Math.round(v - 273.15)} °C)`);
const hours = (v) => {
  if (v == null) return null;
  return v >= 48 ? `${v.toFixed(0)} год (${(v / 24).toFixed(1)} доби)` : `${v.toFixed(1)} год`;
};
const clock = (h) => {
  const m = Math.round(h * 60) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
};
const compass = (az) => ["пн.", "пн.-сх.", "сх.", "пд.-сх.", "пд.", "пд.-зх.", "зх.", "пн.-зх."][Math.round(az / 45) % 8];

function clear() {
  for (const el of root.querySelectorAll("[data-m]")) { el.textContent = "—"; el.className = ""; }
}

function renderMetrics(m) {
  set("local_time", m.local_solar_time_h == null ? "—" : clock(m.local_solar_time_h));
  set("sun_elevation", deg(m.sun_elevation_deg));
  set("sun_azimuth", `${deg(m.sun_azimuth_deg, 1)} (${compass(m.sun_azimuth_deg)})`);
  set("sun_visible", pct(m.sun_visible_fraction), m.sun_visible_fraction > 0 ? "ok" : "no");
  const window = `немає за ${Math.round(m.event_search_hours / 24)} діб`;
  set("sunset", hours(m.hours_to_sunset) ?? window);
  set("sunrise", hours(m.hours_to_sunrise) ?? window);
  set("irradiance", m.solar_irradiance_w_m2 == null ? "—" : `${m.solar_irradiance_w_m2.toFixed(0)} Вт/м²`);
  set("power_vertical", m.panel_power_vertical_w_m2 == null ? "—" : `${m.panel_power_vertical_w_m2.toFixed(0)} Вт`);
  set("power_horizontal", m.panel_power_horizontal_w_m2 == null ? "—" : `${m.panel_power_horizontal_w_m2.toFixed(0)} Вт`);
  set("earth_elevation", deg(m.earth_elevation_deg));
  set("earth_azimuth", `${deg(m.earth_azimuth_deg, 1)} (${compass(m.earth_azimuth_deg)})`);
  set("earth_visible", m.earth_visible ? `так (${pct(m.earth_visible_fraction)} диска)` : "ні", m.earth_visible ? "ok" : "no");
  set("earthset", hours(m.hours_to_earthset) ?? window);
  set("earthrise", hours(m.hours_to_earthrise) ?? window);
  set("earth_distance", km(m.earth_distance_km));
  set("signal_delay", `${m.signal_delay_s.toFixed(3)} с в один бік`);
  const best = (m.stations ?? []).find((s) => s.id === m.recommended_station);
  set("station", best ? best.name : "немає зв'язку", best ? "ok" : "no");
  set("stations", (m.stations ?? []).map((s) =>
    `${s.name.split(" (")[0]}: Місяць ${s.moon_elevation_deg.toFixed(0)}° ${s.available ? "✓" : "✗"}`).join("; ") || "—");
}

function renderElevation(e) {
  set("elevation", `${Math.round(e.height_m).toLocaleString("uk-UA")} м (LOLA ${e.source.id.toUpperCase()}, ${e.source.resolution_m >= 1000 ? (e.source.resolution_m / 1000).toFixed(1) + " км" : Math.round(e.source.resolution_m) + " м"}/пікс.)`);
  set("slope", e.slope_deg == null ? "—" : `${e.slope_deg.toFixed(1)}°, схил на ${compass(e.aspect_deg)} (база ${Math.round(e.slope_baseline_m)} м)`);
}

function renderHorizon(h) {
  set("horizon_max", `${h.max_elevation_deg.toFixed(1)}° (${h.source === "flat" ? "гладка сфера" : "LOLA " + h.source.toUpperCase()})`);
  set("sky_view", pct(h.sky_view_fraction));
  set("dose", `${Math.round(h.gcr_dose_usv_per_day).toLocaleString("uk-UA")} мкЗв/добу (≈ ${Math.round(h.gcr_dose_usv_per_day * 365.25 / 1000)} мЗв/рік)`);
}

function renderTemperature(t) {
  set("temp_now", t.now_k == null ? `немає вимірювань о ${clock(t.local_time_h)}` : `${kelvin(t.now_k)} о ${clock(t.local_time_h)}`);
  set("temp_range", t.min_k == null ? "—" : `${Math.round(t.min_k)}…${Math.round(t.max_k)} K`);
  set("temp_mean", kelvin(t.mean_k));
  set("temp_prp", t.prp ? `${Math.round(t.prp.avg_k)} / ${Math.round(t.prp.max_k)} K` : "поза полярною ділянкою");
  if (!t.prp) set("ice", "немає даних (лише півд. полюс)");
  else if (t.prp.ice_depth_m == null) set("ice", "ні (глибше 2,87 м)", "no");
  else set("ice", t.prp.ice_depth_m === 0 ? "так, на поверхні" : `так, з глибини ${t.prp.ice_depth_m.toFixed(2)} м`, "ok");
}

function renderPeriod(s) {
  set("period_sun", `${hours(s.sun_hours)} (${pct(s.sun_fraction)})`);
  set("period_night", hours(s.longest_night_h));
  set("period_earth", s.earth_fraction == null ? "—" : `${hours(s.earth_hours)} (${pct(s.earth_fraction)})`);
  set("period_comm", `${hours(s.comm_hours)} (${pct(s.comm_fraction)})`, s.comm_fraction > 0 ? "ok" : "no");
  set("period_gap", hours(s.longest_comm_gap_h));
  set("period_energy", s.energy_wh_per_m2 == null ? "—" : `${(s.energy_wh_per_m2 / 1000).toFixed(1)} кВт·год`);
}

let abort = null;
let timer = null;

async function load(url, render, signal, errors, name) {
  try {
    const res = await fetch(url, { signal });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || res.statusText);
    render(body);
  } catch (err) {
    if (err.name !== "AbortError") errors.push(`${name}: ${err.message}`);
  }
}

async function refresh({ lat, lon, datetime, site }) {
  abort?.abort();
  clear();
  if (lat === null || lon === null) {
    set("site", "—");
    status.textContent = "Виберіть місце на Місяці";
    return;
  }
  abort = new AbortController();
  const { signal } = abort;
  set("site", `${site ? site + " · " : ""}${Math.abs(lat).toFixed(4)}° ${lat >= 0 ? "пн." : "пд."}, ${Math.abs(lon).toFixed(4)}° ${lon >= 0 ? "сх." : "зх."}`);
  status.textContent = "Розрахунок…";
  const p = new URLSearchParams({ lat, lon, datetime });
  const point = new URLSearchParams({ lat, lon });
  const start = Date.parse(datetime);
  const end = new Date(start + SYNODIC_MONTH_H * 3600000).toISOString().slice(0, 16) + "Z";
  const period = new URLSearchParams({ lat, lon, start: datetime, end, step_h: 1 });
  const errors = [];
  await Promise.all([
    load(`/api/metrics?${p}`, renderMetrics, signal, errors, "метрики"),
    load(`/api/elevation?${point}`, renderElevation, signal, errors, "рельєф"),
    load(`/api/horizon?${point}`, renderHorizon, signal, errors, "горизонт"),
    load(`/api/temperature?${p}`, renderTemperature, signal, errors, "температура"),
    load(`/api/timeline?${period}`, (t) => renderPeriod(t.summary), signal, errors, "період"),
  ]);
  if (signal.aborted) return;
  status.textContent = errors.length ? `Частина даних недоступна — ${errors.join("; ")}` : "";
}

if (root) {
  subscribe((st) => {
    clearTimeout(timer);
    timer = setTimeout(() => refresh(st), 200);
  });
}
