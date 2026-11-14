// Панель «Місія» (F9) з повзунком «Безпілотна ↔ Пілотована» (F11): конфігуратор складу місії → POST /api/mission.
// Усі числа рахує бекенд (модель M12–M14); тут лише форма, запит і підписи. Коефіцієнти моделі тимчасові —
// про це завжди сказано у виводі. Чисті функції (запит, формати, підписи) — без DOM, тестуються в Node.

import { onLangChange, t } from "./i18n.js";

const STORAGE_KEY = "lse-mission";
const DEBOUNCE_MS = 250;

export const LEVELS = [
  { id: "min", label: "Мінімум" },
  { id: "basic", label: "Базовий" },
  { id: "extended", label: "Розширений" },
  { id: "max", label: "Максимум" },
];

export const DEFAULT_FORM = {
  crewed: false,
  crew: null, // null — людей не вказано явно: кількість задає профіль (і це підсвічується)
  days: 14,
  sizes: { equipment: 1, life_support: 1, comfort: 1 }, // індекси рівнів 0…3
  trajectory: "direct",
  systemId: "",
  siteId: "",
};

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const num = (v, fallback) => (Number.isFinite(Number(v)) && v !== "" && v !== null ? Number(v) : fallback);

// Нормалізує збережену чи введену форму: некоректне → значення за замовчуванням.
export function normalizeForm(raw) {
  const f = structuredClone(DEFAULT_FORM);
  if (!raw || typeof raw !== "object") return f;
  f.crewed = Boolean(raw.crewed);
  f.crew = raw.crew == null || raw.crew === "" ? null : clamp(Math.round(num(raw.crew, 1)), 1, 6);
  f.days = clamp(Math.round(num(raw.days, f.days)), 0, 365);
  for (const key of Object.keys(f.sizes)) f.sizes[key] = clamp(Math.round(num(raw.sizes?.[key], f.sizes[key])), 0, LEVELS.length - 1);
  f.trajectory = raw.trajectory === "low_energy" ? "low_energy" : "direct";
  f.systemId = typeof raw.systemId === "string" ? raw.systemId : "";
  f.siteId = typeof raw.siteId === "string" ? raw.siteId : "";
  return f;
}

// Форма → тіло POST /api/mission (контракт MissionRequest).
export function buildMissionRequest(form) {
  const body = {
    mission_profile: form.crewed ? "crewed" : "uncrewed",
    days: form.crewed ? form.days : 0,
    sizes: Object.fromEntries(Object.entries(form.sizes).map(([k, i]) => [k, LEVELS[clamp(i, 0, LEVELS.length - 1)].id])),
    trajectory: form.trajectory,
  };
  if (form.crewed && form.crew !== null) body.crew = form.crew; // явне значення переважає профіль
  if (form.systemId) body.launch_system_id = form.systemId;
  if (form.siteId) body.launch_site_id = form.siteId;
  return body;
}

const NF = new Intl.NumberFormat("uk-UA", { maximumFractionDigits: 0 });
export const fmtKg = (kg) => `${NF.format(Math.round(kg))} кг`;

// Діапазон вартості у $: одиниця за верхньою межею («млн» або «млрд»).
export function fmtUsdRange(range) {
  const [lo, hi] = range;
  const unit = hi >= 1e9 ? { div: 1e9, name: "млрд" } : { div: 1e6, name: "млн" };
  const f = (v) => {
    const x = v / unit.div;
    return x >= 10 ? NF.format(Math.round(x)) : x.toFixed(1).replace(".", ",");
  };
  return `$${f(lo)}–${f(hi)} ${unit.name}`;
}

const pct = (p) => (p * 100 < 10 ? (p * 100).toFixed(1).replace(".", ",") : String(Math.round(p * 100)));
export const fmtRiskRange = (label, range) => `${label} (${pct(range[0])}–${pct(range[1])} %)`;

export function fmtDaysRange(range) {
  const [lo, hi] = range;
  return lo === hi ? `${NF.format(lo)} діб` : `${NF.format(lo)}–${NF.format(hi)} діб`;
}

// Заповненість ракети: відсотки для смужки (до 100) і підпис; > 100 % — потрібно кілька пусків.
export function fillInfo(cost) {
  const percent = Math.round(cost.utilization * 100);
  // українська множина: 2–4 пуски, 5+ пусків (11–14 — «пусків»)
  const n = cost.launches;
  const few = n % 10 >= 2 && n % 10 <= 4 && !(n % 100 >= 12 && n % 100 <= 14);
  const text = n > 1
    ? t(few ? "{percent} % — потрібно {n} пуски і стикування" : "{percent} % — потрібно {n} пусків і стикування", { percent, n })
    : t("{percent} % місткості на низькій орбіті", { percent });
  return { percent, barPercent: Math.min(100, percent), over: cost.utilization > 1, text };
}

const PROVISIONAL_LABELS = { price_usd_per_kg: "ціна за кг", failure_probability: "ймовірність відмови" };
export function provisionalNotes(response) {
  const notes = [];
  if (response.provisional) notes.push(t("⚠️ Усі коефіцієнти моделі тимчасові (чекають таблиць мас і цін): показано діапазони, а не прогноз."));
  const own = response.launch_system?.provisional_fields ?? [];
  if (own.length) {
    const fields = own.map((f) => t(PROVISIONAL_LABELS[f] ?? f)).join(", ");
    notes.push(t("Для цієї ракети тимчасові: {fields} — у каталозі їх ще немає.", { fields }));
  }
  const fit = response.launch_system?.fit?.note;
  if (fit) notes.push(fit.charAt(0).toUpperCase() + fit.slice(1) + ".");
  return notes;
}

const LIMIT_LABELS = {
  career_effective_dose: "Ефективна доза за кар'єру",
  spe_effective_dose: "Доза від сонячної протонної події",
  bfo_dose_30_day: "Доза на кровотворні органи за 30 діб",
  bfo_dose_1_year: "Доза на кровотворні органи за рік",
  landing_slope_deg: "Нахил майданчика посадки",
  eva_slope_deg: "Нахил для виходу на поверхню",
  lander_tilt_deg: "Нахил модуля після посадки",
  direct_to_earth_comm: "Зв'язок напряму із Землею",
  earth_visible_fraction: "Земля видна",
  sun_visible_fraction: "Сонце видно",
};
const UNIT_LABELS = { deg: "°" };

export function limitText(limit) {
  const label = t(LIMIT_LABELS[limit.quantity] ?? limit.quantity);
  const kind = t(limit.kind === "requirement" ? "вимога" : "фільтр відбору");
  if (limit.value === null || limit.value === undefined) return `${label} (${kind})`;
  const unit = UNIT_LABELS[limit.unit] ?? limit.unit ?? "";
  const space = unit === "°" ? "" : " ";
  return `${label} ${limit.comparison} ${NF.format(limit.value)}${space}${unit} (${kind})`;
}

const PART_LABELS = {
  equipment: "Обладнання", life_support: "Життєзабезпечення", comfort: "Умови й зручності",
  power_system: "Енергетика", structure: "Конструкція", margin: "Запас",
};
export function partsList(masses) {
  return Object.entries(masses).filter(([, v]) => v > 0).map(([k, v]) => `${t(PART_LABELS[k] ?? k)}: ${fmtKg(v)}`);
}

export function profileNote(response) {
  if (!response?.profile) return "";
  const fromProfile = response.profile.from_profile ?? [];
  const set = [];
  if (fromProfile.includes("crew")) set.push(t("кількість людей"));
  if (fromProfile.includes("priorities")) set.push(t("порядок пріоритетів"));
  const limits = fromProfile.filter((f) => f.startsWith("limits.")).length;
  if (limits) set.push(t("{n} порогів", { n: limits }));
  if (!set.length) return "";
  const profile = t(response.profile.profile === "crewed" ? "пілотована" : "безпілотна");
  return t("Профіль «{profile}» задав: {what}. Ваші значення переважають.", { profile, what: set.join(", ") });
}

// ---------- DOM ----------
if (typeof document !== "undefined" && document.getElementById("m-result")) {
  const $ = (id) => document.getElementById(id);
  let form = (() => {
    try { return normalizeForm(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null")); } catch { return normalizeForm(null); }
  })();
  let abort = null;
  let timer = null;
  const markData = (option) => { option.setAttribute("translate", "no"); return option; }; // назви з каталогів
  const save = () => { try { localStorage.setItem(STORAGE_KEY, JSON.stringify(form)); } catch { /* приватний режим */ } };

  function renderForm() {
    $("m-crewed").value = form.crewed ? "1" : "0";
    $("m-crew-row").hidden = !form.crewed;
    $("m-days-row").hidden = !form.crewed;
    if (form.crew !== null) $("m-crew").value = form.crew;
    $("m-days").value = form.days;
    for (const key of Object.keys(form.sizes)) {
      $(`m-size-${key}`).value = form.sizes[key];
      $(`m-size-${key}-out`).textContent = LEVELS[form.sizes[key]].label;
    }
    for (const key of ["life_support", "comfort"]) {
      $(`m-size-${key}`).disabled = !form.crewed;
      $(`m-row-${key}`).classList.toggle("disabled", !form.crewed);
    }
    $("m-size-note").hidden = form.crewed;
    $("m-trajectory").value = form.trajectory;
    $("m-system").value = form.systemId;
    $("m-site").value = form.siteId;
  }

  function renderResult(r) {
    $("m-status").hidden = true;
    const notes = provisionalNotes(r);
    $("m-provisional").hidden = notes.length === 0;
    $("m-provisional").textContent = notes.join(" ");
    $("m-mass-moon").textContent = fmtKg(r.cost.mass_moon_kg);
    $("m-mass-leo").textContent = fmtKg(r.cost.mass_leo_kg);
    $("m-cost").textContent = fmtUsdRange(r.cost.total_usd);
    $("m-risk").textContent = fmtRiskRange(r.risk.band_label, r.risk.p_total_range);
    const crewed = r.risk.p_crew_loss !== null;
    $("m-crew-risk-label").hidden = !crewed;
    $("m-crew-risk").hidden = !crewed;
    if (crewed) $("m-crew-risk").textContent = fmtRiskRange(r.risk.crew_band_label, r.risk.p_crew_loss_range);
    $("m-flight").textContent = fmtDaysRange(r.cost.flight_time_days);
    const fill = fillInfo(r.cost);
    $("m-fill-bar").style.width = `${fill.barPercent}%`;
    $("m-fill-bar").parentElement.classList.toggle("over", fill.over);
    $("m-fill").textContent = fill.text;
    $("m-result").hidden = false;
    $("m-parts").replaceChildren(...partsList(r.payload.masses_kg).map((t) => Object.assign(document.createElement("li"), { textContent: t })));
    // F11: що задав профіль, а не користувач
    const fromProfile = r.profile?.from_profile ?? [];
    $("m-crew-mark").hidden = !(form.crewed && fromProfile.includes("crew"));
    if (form.crewed && form.crew === null) $("m-crew").value = r.profile.crew;
    $("m-profile-note").textContent = profileNote(r);
    const limits = r.profile ? Object.values(r.profile.limits) : [];
    $("m-limits-box").hidden = limits.length === 0;
    $("m-limits").replaceChildren(...limits.map((l) => Object.assign(document.createElement("li"), { textContent: limitText(l) })));
  }

  async function calculate() {
    abort?.abort();
    abort = new AbortController();
    try {
      const res = await fetch("/api/mission", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildMissionRequest(form)), signal: abort.signal,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      lastResponse = data;
      renderResult(data);
    } catch (err) {
      if (err.name === "AbortError") return;
      $("m-result").hidden = true;
      $("m-status").textContent = err.message;
      $("m-status").hidden = false;
    }
  }
  let lastResponse = null;
  onLangChange(() => { if (lastResponse) renderResult(lastResponse); });
  const schedule = () => { save(); clearTimeout(timer); timer = setTimeout(calculate, DEBOUNCE_MS); };

  $("m-crewed").addEventListener("input", (e) => { form.crewed = e.target.value === "1"; if (!form.crewed) form.crew = null; renderForm(); schedule(); });
  $("m-crew").addEventListener("input", (e) => { form.crew = e.target.value === "" ? null : clamp(Math.round(num(e.target.value, 1)), 1, 6); $("m-crew-mark").hidden = true; schedule(); });
  $("m-days").addEventListener("input", (e) => { form.days = clamp(Math.round(num(e.target.value, 0)), 0, 365); schedule(); });
  for (const key of Object.keys(form.sizes)) {
    $(`m-size-${key}`).addEventListener("input", (e) => { form.sizes[key] = Number(e.target.value); renderForm(); schedule(); });
  }
  $("m-trajectory").addEventListener("change", (e) => { form.trajectory = e.target.value; schedule(); });
  $("m-system").addEventListener("change", (e) => { form.systemId = e.target.value; schedule(); });
  $("m-site").addEventListener("change", (e) => { form.siteId = e.target.value; schedule(); });

  (async () => {
    try {
      const [systems, sites] = await Promise.all(["/api/launch-systems", "/api/launch-sites"].map((u) => fetch(u).then((r) => r.json())));
      for (const s of systems.filter((x) => x.capacity_leo_kg)) {
        const state = s.active === false ? ` (${t("не діє")})` : "";
        $("m-system").append(markData(new Option(`${s.name}${state}`, s.id)));
      }
      for (const s of sites) $("m-site").append(markData(new Option(s.name, s.id)));
    } catch { /* без каталогів лишається типова ракета й екватор */ }
    renderForm();
    calculate();
  })();
}
