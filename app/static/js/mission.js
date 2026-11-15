// Панель «Місія» (F9) з повзунком «Безпілотна ↔ Пілотована» (F11): конфігуратор складу місії → POST /api/mission.
// Усі числа рахує бекенд (модель M12–M14); тут лише форма, запит і підписи. Коефіцієнти моделі тимчасові —
// про це завжди сказано у виводі. Чисті функції (запит, формати, підписи) — без DOM, тестуються в Node.

import { onLangChange, t } from "./i18n.js";
import { burnFromMission, saveBurn } from "./selection.js";

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
  useBio: false, // M24: задати біометрію кожної людини
  members: [], // [{sex, age, mass_kg, height_m, activity}]
  supplyDays: null, // на скільки діб везуть запаси; null — рекомендовано
  reservePct: 15, // рекомендований запас, % ⚠️ тимчасово
  supplyKg: { oxygen: null, water: null, food: null }, // П-14: довільні обсяги запасів, кг; null — «авто» (за запасом у добах)
};

export const SEX_LABELS = { male: "чоловік", female: "жінка" };
export const ACTIVITY_LABELS = { sedentary: "малорухомий", low: "помірний", active: "активний", very_active: "дуже активний" };
// Еталонні значення — як на бекенді (app/core/crew.py, ⚠️ не нормативні)
const REFERENCE = { male: { age: 35, mass_kg: 82, height_m: 1.78 }, female: { age: 35, mass_kg: 62, height_m: 1.65 } };
const MEMBER_LIMITS = { age: [19, 80], mass_kg: [35, 160], height_m: [1.4, 2.15] };
export const MAX_CREW = 6;

export function defaultMember(sex = "male") {
  return { sex, ...REFERENCE[sex], activity: "active" };
}

// Нормалізує члена екіпажу: некоректне → еталон статі, числа в межах бекенда.
export function normalizeMember(raw) {
  const sex = raw?.sex === "female" ? "female" : "male";
  const out = { sex, activity: Object.hasOwn(ACTIVITY_LABELS, raw?.activity) ? raw.activity : "active" };
  for (const key of Object.keys(MEMBER_LIMITS)) {
    const [lo, hi] = MEMBER_LIMITS[key];
    const v = Number(raw?.[key]);
    out[key] = Number.isFinite(v) && raw?.[key] !== "" && raw?.[key] !== null ? Math.min(hi, Math.max(lo, v)) : REFERENCE[sex][key];
  }
  return out;
}

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
  f.useBio = Boolean(raw.useBio);
  f.members = Array.isArray(raw.members) ? raw.members.slice(0, MAX_CREW).map(normalizeMember) : [];
  f.supplyDays = raw.supplyDays == null || raw.supplyDays === "" ? null : clamp(num(raw.supplyDays, 0), 0, 365);
  f.reservePct = clamp(num(raw.reservePct, 15), 0, 200);
  for (const key of Object.keys(f.supplyKg)) {
    const v = raw.supplyKg?.[key];
    f.supplyKg[key] = v == null || v === "" ? null : clamp(num(v, 0), 0, 100000);
  }
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
  if (form.crewed && form.useBio && form.members.length) { // M24: біометрія задає людей і запаси
    body.crew_members = form.members.map(normalizeMember);
    delete body.crew;
    if (form.supplyDays !== null) body.supply_days = form.supplyDays;
    if (form.reservePct !== 15) body.reserve_fraction = form.reservePct / 100;
    const kg = Object.fromEntries(Object.entries(form.supplyKg).filter(([, v]) => v !== null));
    if (Object.keys(kg).length) body.supply_kg = kg; // П-14: довільні обсяги окремих запасів
  }
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

const STATUS_LABELS = { in_testing: "випробування", design_target: "проєктна ціль", retired: "знята" };

// Підпис засобу запуску у списку: назва й, коли важливо, статус (проєктні ракети не видаємо за діючі).
export function vehicleLabel(v) {
  const marks = [];
  if (v.catalog === "rockets") {
    if (STATUS_LABELS[v.status]) marks.push(t(STATUS_LABELS[v.status]));
    else if (v.verified_by_flight === false) marks.push(t("не підтверджено польотом"));
  } else if (v.active === false) {
    marks.push(t("не діє"));
  }
  return marks.length ? `${v.name} (${marks.join(", ")})` : v.name;
}

// Для списку: лише засоби з відомою місткістю; діючі й підтверджені польотом — першими.
export function selectableVehicles(list) {
  // 0 — діюча й підтверджена польотом; 1 — діюча, але не підтверджена; 2 — випробування чи проєктна ціль; 3 — не діє
  const rank = (v) => {
    if (v.active === false) return 3;
    if (v.status === "in_testing" || v.status === "design_target") return 2;
    return v.active === true && v.verified_by_flight !== false ? 0 : 1;
  };
  return list.filter((v) => v.capacity_basis).sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name, "uk"));
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
  if (response.launch_system?.rocket?.capacity_basis === "tli") {
    notes.push(t("Місткість ракети дана на траєкторію до Місяця й переведена на низьку орбіту."));
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

// ---------- Числа категорій, запаси й журнал (F19) ----------
const NUM1 = new Intl.NumberFormat("uk-UA", { maximumFractionDigits: 1 });
const SUPPLY_LABELS = { oxygen: "Кисень", water: "Вода", food: "Їжа (з упаковкою)" };
export const supplyLabel = (k) => t(SUPPLY_LABELS[k] ?? k);

// Рядок під повзунком: рівень, маса, вартість, потужність — «що означає ця позначка» у числах.
export function categoryNumbers(cat, levelLabel) {
  if (!cat) return "";
  const power = cat.power_w > 0 ? ` · ${NUM1.format(cat.power_w)} ${t("Вт")}` : "";
  return `${levelLabel}: ${fmtKg(cat.mass_kg)} · ${fmtUsdRange(cat.usd)}${power}`;
}

// Таблиця запасів: що, на добу (кг), завезено, потрібно на місію, рекомендовано, на скільки діб вистачить, баланс (± кг).
export function suppliesRows(cs) {
  if (!cs) return [];
  const signed = (kg) => `${kg > 0.5 ? "+" : ""}${NF.format(Math.round(kg))} ${t("кг")}`;
  return Object.keys(SUPPLY_LABELS).map((k) => {
    const r = cs.resources?.[k];
    return [
      supplyLabel(k),
      `${NUM1.format(cs.per_day[{ oxygen: "oxygen_kg", water: "water_kg", food: "food_kg" }[k]])} ${t("кг")}`,
      fmtKg(cs.loaded_kg[k]),
      fmtKg(cs.required_kg[k]),
      r ? fmtKg(r.recommended_kg) : "—",
      r && Number.isFinite(r.covers_days) && r.covers_days < 1e6 ? NUM1.format(r.covers_days) : "—",
      r ? signed(r.balance_kg) : "—",
    ];
  });
}

// Гроші без «млн»-округлення для малих сум: $12 тис., $1,2 млн.
export function fmtUsdAny(range) {
  const [lo, hi] = range;
  const unit = hi >= 1e9 ? { div: 1e9, name: "млрд" } : hi >= 1e6 ? { div: 1e6, name: "млн" } : hi >= 1e3 ? { div: 1e3, name: "тис." } : { div: 1, name: "" };
  const f = (v) => { const x = v / unit.div; return x >= 10 ? NF.format(Math.round(x)) : x.toFixed(1).replace(".", ","); };
  return `$${f(lo)}–${f(hi)}${unit.name ? ` ${t(unit.name)}` : ""}`;
}

// Підсумок запасів для планувальника: чи вистачає, де закінчиться, скільки зайвого й скільки грошей це коштує.
export function summaryLines(r) {
  const cs = r?.crew_supplies;
  if (!cs?.summary) return [];
  const s = cs.summary, eco = cs.economics;
  const out = [];
  if (s.mission_ok) out.push({ kind: "ok", text: t("Запасів життєзабезпечення вистачає на всю місію.") });
  else {
    out.push({ kind: "crit", text: t("Місія не виконується: {res} закінчується на добі {day} з {days}.", {
      res: supplyLabel(s.first_shortage_resource).toLowerCase(), day: NUM1.format(s.first_shortage_day), days: NUM1.format(cs.days) }) });
  }
  if (s.deficit_kg > 0.05) {
    out.push({ kind: "crit", text: t("Нестача: {kg}; щоб закрити, треба ≈ {usd}.", {
      kg: fmtKg(s.deficit_kg), usd: eco ? fmtUsdAny(eco.deficit_usd) : "—" }) });
  }
  if (s.excess_kg > 0.05) {
    out.push({ kind: "warn", text: t("Надлишок понад потребу й резерв: {kg} — зайві гроші ≈ {usd}.", {
      kg: fmtKg(s.excess_kg), usd: eco ? fmtUsdAny(eco.excess_usd) : "—" }) });
  }
  if (eco) out.push({ kind: "", text: t("Усі запаси разом: {kg}, ≈ {usd} (ціни тимчасові).", { kg: fmtKg(cs.loaded_total_kg), usd: fmtUsdAny(eco.loaded_usd) }) });
  return out;
}

// Повзунок запасу в кг: межі, крок, значення, позначка «рекомендовано» і підпис (авто — значення рахує сервер).
export function supplySlider(cs, key, userKg) {
  const r = cs?.resources?.[key];
  if (!r) return null;
  const rec = r.recommended_kg;
  const value = userKg ?? r.loaded_kg;
  const max = Math.max(1, Math.ceil(Math.max(rec * 2, value * 1.05)));
  const step = max <= 40 ? 0.1 : max <= 400 ? 1 : 5;
  const status = r.runs_out_day !== null ? "shortage" : value < rec - 1e-9 ? "reserve" : r.excess_kg > 0.05 ? "excess" : "ok";
  return { min: 0, max, step, value: Math.round(value * 10) / 10, rec: Math.round(rec * 10) / 10, auto: userKg == null, status,
           text: `${NUM1.format(value)} ${t("кг")} · ${t("рекомендовано")} ${NUM1.format(rec)} ${t("кг")}` };
}

// Підсумок запасу: «рекомендовано 23 доби, заплановано 23 доби (резерв 15 %)».
export function reserveText(cs) {
  if (!cs) return "";
  const planned = cs.reserve_fraction_planned == null ? "—" : `${Math.round(cs.reserve_fraction_planned * 100)} %`;
  return t("Рекомендовано {rec} діб (резерв {rp} %), заплановано {plan} діб (резерв {pp}).", {
    rec: NUM1.format(cs.recommended_supply_days), rp: Math.round(cs.reserve_fraction_recommended * 100),
    plan: NUM1.format(cs.supply_days), pp: planned,
  });
}

// Журнал розходу: рядок на добу (або рідше для довгих місій); кожна клітинка — відсоток і стан.
export function logRows(cs, maxRows = 40) {
  const log = cs?.log ?? [];
  const stride = Math.max(1, Math.ceil(log.length / maxRows));
  return log.filter((e, i) => i % stride === 0 || i === log.length - 1).map((e) => ({
    worst: e.worst,
    cells: [NUM1.format(e.day), ...Object.keys(SUPPLY_LABELS).map((k) => `${NUM1.format(e.remaining_pct[k])} %`)],
    status: Object.keys(SUPPLY_LABELS).map((k) => e.status[k]),
  }));
}

export const warningTexts = (cs) => (cs?.warnings ?? []).map((w) => w.message);

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
    // M24: редактор екіпажу
    $("m-bio-box").hidden = !form.crewed;
    $("m-bio").checked = form.useBio;
    $("m-bio-fields").hidden = !(form.crewed && form.useBio);
    $("m-supply-days").value = form.supplyDays ?? "";
    $("m-reserve").value = form.reservePct;
    for (const key of Object.keys(form.supplyKg)) $(`m-kg-${key}-auto`).disabled = form.supplyKg[key] === null;
    renderMembers();
  }

  function renderMembers() {
    const box = $("m-members");
    box.replaceChildren(...form.members.map((m, i) => {
      const row = document.createElement("div");
      row.className = "member-row";
      const field = (key, label, attrs) => {
        const lab = document.createElement("label");
        lab.append(t(label), " ");
        const input = Object.assign(document.createElement("input"), { type: "number", value: m[key], ...attrs });
        input.addEventListener("change", () => { form.members[i] = normalizeMember({ ...form.members[i], [key]: input.value }); renderMembers(); schedule(); });
        lab.append(input);
        return lab;
      };
      const selectOf = (key, label, labels) => {
        const lab = document.createElement("label");
        lab.append(t(label), " ");
        const sel = document.createElement("select");
        for (const [v, text] of Object.entries(labels)) sel.append(new Option(t(text), v, false, m[key] === v));
        sel.addEventListener("change", () => {
          form.members[i] = key === "sex" ? { ...defaultMember(sel.value), activity: m.activity } : { ...m, [key]: sel.value };
          renderMembers(); schedule();
        });
        lab.append(sel);
        return lab;
      };
      const remove = Object.assign(document.createElement("button"), { type: "button", textContent: "×", title: t("Прибрати людину") });
      remove.addEventListener("click", () => { form.members.splice(i, 1); form.crew = form.members.length || null; renderForm(); schedule(); });
      row.append(selectOf("sex", "Стать", SEX_LABELS), field("age", "Вік", { min: 19, max: 80, step: 1 }),
        field("mass_kg", "Маса, кг", { min: 35, max: 160, step: 1 }), field("height_m", "Зріст, м", { min: 1.4, max: 2.15, step: 0.01 }),
        selectOf("activity", "Активність", ACTIVITY_LABELS), remove);
      return row;
    }));
    $("m-add-member").disabled = form.members.length >= MAX_CREW;
  }

  function renderSupplies(r) {
    const cs = r.crew_supplies;
    $("m-supplies").hidden = !cs;
    for (const key of Object.keys(form.sizes)) {
      $(`m-num-${key}`).textContent = categoryNumbers(r.categories?.[key], LEVELS[form.sizes[key]].label);
    }
    if (!cs) return;
    const summary = summaryLines(r);
    $("m-supply-summary").replaceChildren(...summary.map((l) => Object.assign(document.createElement("li"), { textContent: l.text, className: `supply-${l.kind || "info"}` })));
    for (const key of Object.keys(form.supplyKg)) {
      const s = supplySlider(cs, key, form.supplyKg[key]);
      if (!s) continue;
      const range = $(`m-kg-${key}`);
      if (document.activeElement !== range) { range.max = s.max; range.step = s.step; range.value = s.value; }
      range.dataset.status = s.status;
      $(`m-kg-${key}-mark`).replaceChildren(Object.assign(document.createElement("option"), { value: Math.min(s.rec, s.max) }));
      $(`m-kg-${key}-out`).textContent = s.text;
      $(`m-kg-${key}-out`).dataset.status = s.status;
      $(`m-kg-${key}-auto`).disabled = s.auto;
    }
    const warn = warningTexts(cs);
    $("m-supply-warn").hidden = warn.length === 0;
    $("m-supply-warn").textContent = warn.join(" ");
    $("m-supply-reserve").textContent = reserveText(cs);
    const cell = (text, cls) => Object.assign(document.createElement("td"), { textContent: text, className: cls ?? "" });
    $("m-supply-table").tBodies[0].replaceChildren(...suppliesRows(cs).map((row) => {
      const tr = document.createElement("tr");
      tr.append(...row.map((c) => cell(c)));
      return tr;
    }));
    const STATUS = { ok: "", reserve: "supply-reserve", shortage: "supply-shortage" };
    $("m-log").tBodies[0].replaceChildren(...logRows(cs).map((row) => {
      const tr = document.createElement("tr");
      tr.className = STATUS[row.worst];
      tr.append(cell(row.cells[0]), ...row.cells.slice(1).map((c, i) => cell(c, STATUS[row.status[i]])));
      return tr;
    }));
  }

  function renderResult(r) {
    $("m-status").hidden = true;
    saveBurn(burnFromMission(r)); // «Система» анімує розгін за масою цієї місії (G16)
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
    renderSupplies(r);
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
  $("m-bio").addEventListener("change", (e) => {
    form.useBio = e.target.checked;
    if (form.useBio && !form.members.length) { // перший раз — стільки людей, скільки в профілі (інакше 2)
      const n = clamp(form.crew ?? 2, 1, MAX_CREW);
      form.members = Array.from({ length: n }, (_, i) => defaultMember(i % 2 ? "female" : "male"));
    }
    if (form.useBio) form.crew = form.members.length;
    renderForm(); schedule();
  });
  $("m-add-member").addEventListener("click", () => {
    if (form.members.length >= MAX_CREW) return;
    form.members.push(defaultMember(form.members.length % 2 ? "female" : "male"));
    form.crew = form.members.length; renderForm(); schedule();
  });
  $("m-supply-days").addEventListener("input", (e) => { form.supplyDays = e.target.value === "" ? null : clamp(num(e.target.value, 0), 0, 365); schedule(); });
  $("m-reserve").addEventListener("input", (e) => { form.reservePct = clamp(num(e.target.value, 15), 0, 200); schedule(); });
  for (const key of Object.keys(form.supplyKg)) { // П-14: довільні обсяги запасів, кг; «Авто» повертає розрахунок за добами
    $(`m-kg-${key}`).addEventListener("input", (e) => { form.supplyKg[key] = clamp(num(e.target.value, 0), 0, 100000); $(`m-kg-${key}-auto`).disabled = false; schedule(); });
    $(`m-kg-${key}-auto`).addEventListener("click", () => { form.supplyKg[key] = null; $(`m-kg-${key}-auto`).disabled = true; schedule(); });
  }
  $("m-trajectory").addEventListener("change", (e) => { form.trajectory = e.target.value; schedule(); });
  $("m-system").addEventListener("change", (e) => { form.systemId = e.target.value; schedule(); });
  $("m-site").addEventListener("change", (e) => { form.siteId = e.target.value; schedule(); });

  (async () => {
    try {
      const [systems, sites] = await Promise.all(["/api/launch-systems", "/api/launch-sites"].map((u) => fetch(u).then((r) => r.json())));
      for (const v of selectableVehicles(systems)) $("m-system").append(markData(new Option(vehicleLabel(v), v.id)));
      for (const s of sites) $("m-site").append(markData(new Option(s.name, s.id)));
    } catch { /* без каталогів лишається типова ракета й екватор */ }
    renderForm();
    calculate();
  })();
}
