// Вкладка «План місії» (F16): вимоги до місця посадки + склад місії + ракета → POST /api/plan (B18) → таблиця варіантів
// з виділеним автовибором. Усе рахує бекенд; тут форма, запит і підписи. Чисті функції — без DOM, тестуються в Node.
import { getState, setState } from "./state.js";
import { onLangChange, t } from "./i18n.js";

export const DEFAULT_FORM = {
  profile: "uncrewed", crew: null, days: 5,
  regionLatMin: -90, regionLatMax: -80, gridStep: 2, periodDays: 10,
  minSunHours: null, minCommHours: null, maxSlope: null, minEarth: null, minSun: null,
  vehicle: "any", trajectory: "any", plans: 5, departureDays: 7,
};

const REQUIREMENT_LABELS = {
  min_sun_hours: "Сонце, год",
  min_comm_hours: "Зв'язок, год",
  max_slope_deg: "Нахил, °",
  min_earth_fraction: "Земля видна",
  min_sun_fraction: "Сонце видно",
};
export const requirementLabel = (key) => t(REQUIREMENT_LABELS[key] ?? key);

const num = (v) => (v === null || v === undefined || v === "" || !Number.isFinite(Number(v)) ? null : Number(v));
const iso = (ms) => new Date(ms).toISOString().replace(/\.\d+Z$/, "Z");

// Форма й спільний стан (дата календаря) → тіло POST /api/plan (контракт PlanRequest).
export function buildPlanRequest(form, state) {
  const startMs = Date.parse(state.datetime);
  if (!Number.isFinite(startMs)) throw new Error("bad datetime");
  const days = Math.min(Math.max(Math.round(num(form.periodDays) ?? 10), 1), 60);
  const body = {
    start: iso(startMs),
    end: iso(startMs + days * 86400000),
    region: { lat_min: num(form.regionLatMin) ?? -90, lat_max: num(form.regionLatMax) ?? -80, lon_min: -180, lon_max: 180 },
    grid_step_deg: num(form.gridStep) ?? 2,
    mission_profile: form.profile,
    days: form.profile === "crewed" ? num(form.days) ?? 0 : 0,
    limit: num(form.plans) ?? 5,
    departure_days: Math.min(Math.max(Math.round(num(form.departureDays) ?? 1), 1), 60),
  };
  if (form.profile === "crewed" && num(form.crew) !== null) body.crew = Number(form.crew);
  const reqs = { min_sun_hours: form.minSunHours, min_comm_hours: form.minCommHours, max_slope_deg: form.maxSlope,
                 min_earth_fraction: form.minEarth, min_sun_fraction: form.minSun };
  for (const [key, value] of Object.entries(reqs)) if (num(value) !== null) body[key] = Number(value);
  if (form.vehicle && form.vehicle !== "any") body.vehicle = form.vehicle;
  if (form.trajectory && form.trajectory !== "any") body.trajectories = [form.trajectory];
  return body;
}

const fmt = (v, d = 0) => (v == null ? "—" : Number(v).toLocaleString("uk-UA", { maximumFractionDigits: d }));
const usd = (range) => (range ? `${fmt(range[0] / 1e6, 1)}–${fmt(range[1] / 1e6, 1)} ${t("млн $")}` : "—");
const place = (site) => site.name ?? `${site.lat.toFixed(2)}°, ${site.lon.toFixed(2)}°`;

// Статус вимог плану: «виконано», «порушено: …», «не перевірено: …».
export function requirementsText(req) {
  const parts = [];
  if (!req.feasible) {
    parts.push(`${t("порушено")}: ${req.violations.map((v) => `${requirementLabel(v.requirement)} ${fmt(v.value, 1)} ${t("замість")} ${fmt(v.required, 1)}`).join("; ")}`);
  } else parts.push(t("виконано"));
  if (req.warnings.length) parts.push(`${t("м'які")}: ${req.warnings.map((w) => requirementLabel(w.requirement)).join(", ")}`);
  if (req.unchecked.length) parts.push(`${t("не перевірено")}: ${req.unchecked.map(requirementLabel).join(", ")}`);
  return parts.join(" · ");
}

// Рядки таблиці варіантів (усі значення — текст, без undefined/NaN).
export function planRows(response) {
  return (response?.plans ?? []).map((p) => {
    const launch = p.launch;
    return {
      rank: p.rank,
      lead: p.rank === response.auto_selected,
      feasible: p.requirements.feasible,
      lat: p.landing.moon_site.lat,
      lon: p.landing.moon_site.lon,
      cells: [
        String(p.rank),
        place(p.landing.moon_site),
        `${fmt(p.score_pct, 1)} %`,
        requirementsText(p.requirements),
        launch ? launch.site.name : "—",
        p.route ? p.route.departure_utc.slice(0, 10) : "—",
        launch ? launch.vehicle.name : t("немає варіанта, що вміщує масу"),
        launch ? launch.trajectory : "—",
        launch ? `${fmt(launch.duration_days[0], 1)}–${fmt(launch.duration_days[1], 1)} ${t("діб")}` : "—",
        launch ? usd(launch.launch_cost_usd) : "—",
        launch ? `${fmt(launch.risk.p * 100, 1)} % · ${launch.risk.band_label}` : "—",
        `${fmt(p.mass_moon_kg)} ${t("кг")}`,
      ],
    };
  });
}

// --- DOM ------------------------------------------------------------------------------------------------------

function init() {
  const $ = (id) => document.getElementById(id);
  const form = $("plan-form");
  if (!form) return;
  const status = $("plan-status");
  const table = $("plan-table");
  const lead = $("plan-explanation");
  const actions = $("plan-actions");
  let controller = null;
  let last = null;

  const read = () => ({
    profile: $("plan-profile").value, crew: $("plan-crew").value, days: $("plan-days").value,
    regionLatMin: $("plan-lat-min").value, regionLatMax: $("plan-lat-max").value, gridStep: $("plan-grid").value,
    periodDays: $("plan-period").value, minSunHours: $("plan-min-sun-hours").value,
    minCommHours: $("plan-min-comm-hours").value, maxSlope: $("plan-max-slope").value,
    minEarth: $("plan-min-earth").value, minSun: $("plan-min-sun").value,
    vehicle: $("plan-vehicle").value, trajectory: $("plan-trajectory").value, plans: 5,
    departureDays: $("plan-departure-days").value,
  });

  const syncProfile = () => {
    for (const el of document.querySelectorAll(".plan-crewed")) el.hidden = $("plan-profile").value !== "crewed";
  };

  const render = (response) => {
    last = response;
    lead.textContent = response.explanation;
    lead.hidden = false;
    table.tBodies[0].replaceChildren(...planRows(response).map((r) => {
      const tr = document.createElement("tr");
      if (r.lead) tr.className = "best";
      if (!r.feasible) tr.classList.add("infeasible");
      for (const c of r.cells) {
        const td = document.createElement("td");
        td.textContent = c;
        tr.append(td);
      }
      const td = document.createElement("td");
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = t("На Місяці");
      b.addEventListener("click", () => {
        setState({ lat: r.lat, lon: r.lon, site: response.plans[r.rank - 1].landing.moon_site.site_id ?? null });
        window.location.href = `/moon${window.location.search}`;
      });
      td.append(b);
      tr.append(td);
      return tr;
    }));
    table.hidden = false;
    actions.hidden = response.plans.length === 0;
  };

  const run = async () => {
    let body;
    try { body = buildPlanRequest(read(), getState()); } catch { status.textContent = t("Вкажіть дату в календарі."); return; }
    controller?.abort();
    controller = new AbortController();
    status.textContent = t("Рахую план місії… це може тривати до пів хвилини.");
    $("plan-run").disabled = true;
    try {
      const res = await fetch("/api/plan", { method: "POST", headers: { "Content-Type": "application/json" },
                                             body: JSON.stringify(body), signal: controller.signal });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? `HTTP ${res.status}`);
      status.textContent = data.grid.truncated ? t("Сітку оцінено не повністю: вичерпано бюджет часу.") : "";
      render(data);
    } catch (err) {
      if (err.name !== "AbortError") status.textContent = `${t("Помилка")}: ${err.message}`;
    } finally {
      $("plan-run").disabled = false;
    }
  };

  $("plan-flight").addEventListener("click", () => { window.location.href = `/system${window.location.search}`; });
  $("plan-profile").addEventListener("change", syncProfile);
  form.addEventListener("submit", (e) => { e.preventDefault(); run(); });
  syncProfile();
  fetch("/api/launch-systems").then((r) => r.json()).then((list) => {
    const sel = $("plan-vehicle");
    for (const v of list.filter((x) => x.capacity_basis)) sel.append(new Option(v.name, v.id));
  }).catch(() => {});
  onLangChange(() => { if (last) render(last); });
}

if (typeof document !== "undefined") init();
