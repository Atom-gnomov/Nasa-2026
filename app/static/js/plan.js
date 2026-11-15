// Вкладка «План місії» (F16): вимоги до місця посадки + склад місії + ракета → POST /api/plan (B18) → таблиця варіантів
// з виділеним автовибором. Усе рахує бекенд; тут форма, запит і підписи. Чисті функції — без DOM, тестуються в Node.
import { getState, setState } from "./state.js";
import { onLangChange, t } from "./i18n.js";
import { burnFromMission, leadFromPlan, loadMissionForm, planFieldsFromMission, saveBurn, saveLead } from "./selection.js";
import { DEFAULT_FORM as SEARCH_DEFAULTS } from "./search.js";
import { loadLaunch, loadSearchForm, plainSite, planRequirements, requirementsSummary, saveLaunch } from "./pipeline.js";

export const DEFAULT_FORM = {
  profile: "uncrewed", crew: null, days: 5,
  // Вимоги до місця посадки (область, сітка, період, пороги, пріоритети) тут не вводяться: беруться з «Підбору» (F20)
  launchSite: "", // майданчик старту: "" — підібрати автоматично; id — лише з нього (спільний вибір для вкладок)
  vehicle: "any", trajectory: "any", plans: 5,
  includeDesign: true, multiLaunch: false,
  members: null, supplyDays: null, reservePct: 15, // екіпаж із біометрією (F18/F19: з вкладки «Місія»)
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

// Вимоги з «Підбору» (searchForm), склад місії й ракета з форми, дата з календаря → тіло POST /api/plan (PlanRequest).
export function buildPlanRequest(form, state, searchForm = null) {
  const startMs = Date.parse(state.datetime);
  if (!Number.isFinite(startMs)) throw new Error("bad datetime");
  const base = planRequirements({ ...structuredClone(SEARCH_DEFAULTS), ...(searchForm ?? {}) }, state.datetime);
  const body = {
    ...base,
    mission_profile: form.profile,
    days: form.profile === "crewed" ? num(form.days) ?? 0 : 0,
    limit: num(form.plans) ?? 5,
    departure_days: 1, // старт підлаштовується під дату посадки (календар): перебору інших дат немає
  };
  if (form.profile === "crewed" && num(form.crew) !== null) body.crew = Number(form.crew);
  if (plainSite(form.launchSite)) body.launch_site_id = form.launchSite;
  // Точку посадки вже вибрано на кроці 5 — оцінюємо лише її (не шукаємо знову по області)
  if (form.useChosenPoint !== false && state.lat != null && state.lon != null) {
    body.landing_point = { lat: Number(state.lat), lon: Number(state.lon) };
    if (state.site) body.landing_point.site_id = state.site;
  }
  if (form.vehicle && form.vehicle !== "any") body.vehicle = form.vehicle;
  // Календар — дата посадки, старт підлаштовується: маршрут завжди явний (швидкий — прямий, економний — ≈ 105 діб до посадки)
  body.trajectories = [form.profile === "crewed" || form.trajectory !== "low_energy" ? "direct" : "low_energy"];
  if (form.profile === "crewed" && Array.isArray(form.members) && form.members.length) {
    body.crew_members = form.members;
    delete body.crew;
    if (num(form.supplyDays) !== null) body.supply_days = Number(form.supplyDays);
    if (num(form.reservePct) !== null && Number(form.reservePct) !== 15) body.reserve_fraction = Number(form.reservePct) / 100;
  }
  if (form.includeDesign === false) body.include_design_targets = false;
  if (form.multiLaunch === true) body.allow_multiple_launches = true;
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

// Заповненість ракети (місткість): відсоток і, коли треба, кілька пусків — для порівняння носіїв (F27).
export function fillText(launch) {
  if (!launch || !Number.isFinite(launch.utilization)) return "—";
  const pct = `${fmt(launch.utilization * 100, 0)} %`;
  return launch.launches > 1 ? `${pct} · ${launch.launches} ${t("пуски")}` : pct;
}

// Вибір носія з таблиці (F27): майданчик, ракета, траєкторія й дата старту — у спільний вибір польоту (F20).
export function launchChoiceFromPlan(plan) {
  const l = plan?.launch;
  if (!l) return null;
  return { site: l.site.id, vehicle: l.vehicle.id, trajectory: l.trajectory, departure: plan.route?.departure_utc?.slice(0, 10) ?? "" };
}

// Дата й час старту: «2026-12-05 14:22 UTC»; без точного моменту (немає вікна запуску) — лише дата.
export function launchMoment(plan) {
  const iso = plan?.route?.departure_utc;
  if (!iso) return "—";
  const date = iso.slice(0, 10), time = iso.slice(11, 16);
  return plan.launch_windows_utc?.length && time !== "00:00" ? `${date} ${time} UTC` : date;
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
        launchMoment(p),
        launch ? launch.vehicle.name : t("немає варіанта, що вміщує масу"),
        fillText(launch),
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
  let chosenRank = null; // F27: варіант, який користувач обрав у таблиці; без вибору йде автовибір

  const read = () => ({
    profile: $("plan-profile").value, crew: $("plan-crew").value, days: $("plan-days").value,
    launchSite: $("plan-site").value, useChosenPoint: !$("plan-research").checked,
    vehicle: $("plan-vehicle").value, trajectory: $("plan-trajectory").value, plans: 5,
    includeDesign: $("plan-design").checked, multiLaunch: $("plan-multi").checked,
    members: prefill?.members ?? null, supplyDays: prefill?.supplyDays ?? null, reservePct: prefill?.reservePct ?? 15,
  });

  const syncProfile = () => {
    const crewed = $("plan-profile").value === "crewed";
    for (const el of document.querySelectorAll(".plan-crewed")) el.hidden = !crewed;
    // пілотована місія — лише пряма траєкторія (планувальник так і розглядає)
    if (crewed) $("plan-trajectory").value = "direct";
    $("plan-trajectory").disabled = crewed;
  };

  const render = (response) => {
    last = response;
    const leader = leadFromPlan(response, chosenRank);
    if (leader) {
      saveLead(leader); // «Система» й «Вікно запуску» покажуть цей майданчик і траєкторію, якщо вибір не зроблено вручну
      const mission = (response.plans.find((p) => p.rank === (chosenRank ?? response.auto_selected)) ?? response.plans[0])?.mission;
      if (mission) saveBurn(burnFromMission(mission)); // «Система» анімує розгін за масою лідера
      setState({ site: leader.moon.site, lat: leader.moon.lat, lon: leader.moon.lon }); // точка на «Місяці» — лідер плану
    }
    const sp = response.surface_period;
    const period = sp ? ` ${t("Місце оцінено за період")} ${sp.start.slice(0, 10)} – ${sp.end.slice(0, 10)}${sp.after_arrival ? ` (${t("після прибуття")})` : ""}.` : "";
    const supply = (response.plans?.[0]?.mission?.crew_supplies?.warnings ?? []).map((w) => `⚠ ${w.message}`);
    lead.textContent = [response.explanation + period, ...supply, ...(response.notes ?? [])].join(" ");
    lead.hidden = false;
    table.tBodies[0].replaceChildren(...planRows(response).map((r) => {
      const tr = document.createElement("tr");
      if (r.lead) tr.className = "best";
      if (r.rank === (chosenRank ?? response.auto_selected)) tr.classList.add("chosen");
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
      const choice = launchChoiceFromPlan(response.plans[r.rank - 1]);
      const pick = document.createElement("button");
      pick.type = "button";
      pick.textContent = t(tr.classList.contains("chosen") ? "Обрано" : "Обрати");
      pick.disabled = !choice || tr.classList.contains("chosen");
      pick.title = t("Цей варіант піде далі: у «Систему», перевірку й звіт");
      pick.addEventListener("click", () => { chosenRank = r.rank; saveLaunch(choice); render(response); });
      td.append(pick, " ", b);
      tr.append(td);
      return tr;
    }));
    table.hidden = false;
    actions.hidden = response.plans.length === 0;
  };

  const run = async () => {
    let body;
    try { body = buildPlanRequest(read(), getState(), loadSearchForm()); } catch { status.textContent = t("Вкажіть дату в календарі."); return; }
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
      chosenRank = null;
      render(data);
    } catch (err) {
      if (err.name !== "AbortError") status.textContent = `${t("Помилка")}: ${err.message}`;
    } finally {
      $("plan-run").disabled = false;
    }
  };

  // F18: профіль, екіпаж беремо з вкладки «Місія»; F20: майданчик, траєкторія й ракета — спільний вибір польоту
  const prefill = planFieldsFromMission(loadMissionForm());
  if (prefill) {
    $("plan-profile").value = prefill.profile;
    if (prefill.crew) $("plan-crew").value = prefill.crew;
    if (prefill.days != null) $("plan-days").value = prefill.days;
    $("plan-prefill").hidden = false;
  }
  const launch = loadLaunch();
  $("plan-trajectory").value = launch.trajectory === "low_energy" ? "low_energy" : "direct";
  $("plan-trajectory").addEventListener("change", (e) => { if (!e.target.disabled) saveLaunch({ trajectory: e.target.value }); });
  $("plan-vehicle").addEventListener("change", (e) => saveLaunch({ vehicle: e.target.value }));
  $("plan-site").addEventListener("change", (e) => saveLaunch({ site: e.target.value }));
  $("plan-research").addEventListener("change", () => renderRequirements());

  // Вимоги до місця посадки — з «Підбору» (читаємо щоразу, коли повертаємось на вкладку)
  const renderRequirements = () => {
    const st = getState();
    const point = st.lat != null && st.lon != null && !$("plan-research").checked ? { lat: st.lat, lon: st.lon } : null;
    $("plan-research-row").hidden = st.lat == null || st.lon == null;
    const rows = requirementsSummary(loadSearchForm() ?? SEARCH_DEFAULTS, point);
    $("plan-req").replaceChildren(...rows.flatMap(([name, value]) => {
      const dt = Object.assign(document.createElement("dt"), { textContent: t(name) });
      const dd = Object.assign(document.createElement("dd"), { textContent: value });
      return [dt, dd];
    }));
  };
  renderRequirements();
  window.addEventListener("pageshow", renderRequirements);
  window.addEventListener("storage", renderRequirements);

  $("plan-flight").addEventListener("click", () => { window.location.href = `/system${window.location.search}`; });
  $("plan-profile").addEventListener("change", syncProfile);
  form.addEventListener("submit", (e) => { e.preventDefault(); run(); });
  syncProfile();
  fetch("/api/launch-systems").then((r) => r.json()).then((list) => {
    const sel = $("plan-vehicle");
    for (const v of list.filter((x) => x.capacity_basis)) sel.append(new Option(v.name, v.id));
    if (launch.vehicle !== "any" && [...sel.options].some((o) => o.value === launch.vehicle)) sel.value = launch.vehicle;
  }).catch(() => {});
  fetch("/api/launch-sites").then((r) => r.json()).then((list) => {
    const sel = $("plan-site");
    for (const x of list) sel.append(Object.assign(new Option(x.name.split(" (")[0], x.id), {}));
    const chosen = plainSite(launch.site);
    if (chosen && [...sel.options].some((o) => o.value === chosen)) sel.value = chosen;
  }).catch(() => {});
  onLangChange(() => { if (last) render(last); });
}

if (typeof document !== "undefined") init();
