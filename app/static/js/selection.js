// Наскрізний вибір між вкладками (F18): що користувач обрав на одній вкладці, підставляється в поля інших.
// «Місія» зберігає форму в localStorage ("lse-mission"); «План місії» після розрахунку лишає лідера в "lse-plan-lead";
// «Система» бере з них майданчик і траєкторію. Чисті функції — без DOM, тестуються в Node.

export const MISSION_KEY = "lse-mission";
export const PLAN_LEAD_KEY = "lse-plan-lead";
const TRAJECTORIES = ["direct", "low_energy"];

const read = (key) => {
  try { return JSON.parse(globalThis.localStorage?.getItem(key) ?? "null"); } catch { return null; }
};
const write = (key, value) => {
  try { globalThis.localStorage?.setItem(key, JSON.stringify(value)); } catch { /* сховище недоступне — не критично */ }
};

// Збережена форма «Місії» → значення полів «Плану місії» (профіль, екіпаж, доби, ракета, траєкторія); null — нема що брати.
export function planFieldsFromMission(raw) {
  if (!raw || typeof raw !== "object") return null;
  const out = { profile: raw.crewed ? "crewed" : "uncrewed", vehicle: typeof raw.systemId === "string" && raw.systemId ? raw.systemId : "any" };
  const crew = Number(raw.crew);
  if (raw.crewed && Number.isInteger(crew) && crew >= 1 && crew <= 6) out.crew = crew;
  const days = Number(raw.days);
  if (raw.crewed && Number.isFinite(days) && days >= 0 && days <= 365) out.days = days;
  if (TRAJECTORIES.includes(raw.trajectory)) out.trajectory = raw.trajectory;
  if (raw.crewed && raw.useBio && Array.isArray(raw.members) && raw.members.length) { // M24: екіпаж із біометрією
    out.members = raw.members.slice(0, 6);
    if (raw.supplyDays != null) out.supplyDays = Number(raw.supplyDays);
    if (Number.isFinite(Number(raw.reservePct))) out.reservePct = Number(raw.reservePct);
  }
  return out;
}

// Відповідь /api/plan → що запам'ятати про лідера плану (майданчик, ракета, траєкторія, точка на Місяці).
// rank — номер варіанта, який обрав користувач у таблиці порівняння (F27); без нього — автовибір планувальника.
export function leadFromPlan(response, rank = null) {
  const plans = response?.plans ?? [];
  const plan = (rank != null && plans.find((p) => p.rank === rank)) || plans.find((p) => p.rank === response?.auto_selected) || plans[0];
  if (!plan) return null;
  const site = plan.landing.moon_site;
  return {
    siteId: plan.launch?.site?.id ?? null, vehicleId: plan.launch?.vehicle?.id ?? null,
    trajectory: plan.launch?.trajectory ?? null,
    moon: { site: site.site_id ?? null, lat: site.lat, lon: site.lon },
  };
}

// Майданчик і траєкторія для «Вікна запуску»: лідер плану, інакше те, що вибрано в «Місії».
export function launchChoice(lead, missionRaw) {
  const siteId = lead?.siteId || (typeof missionRaw?.siteId === "string" && missionRaw.siteId) || null;
  const trajectory = [lead?.trajectory, missionRaw?.trajectory].find((t) => TRAJECTORIES.includes(t)) ?? null;
  const source = lead?.siteId ? "plan" : siteId ? "mission" : null;
  return { siteId, trajectory, source };
}

export const BURN_KEY = "lse-burn";
// Розгін TLI з відповіді /api/mission (flight_phases.tli) — для анімації польоту у вкладці «Система» (G16).
export const burnFromMission = (response) => response?.flight_phases?.tli ?? null;
export const saveBurn = (burn) => write(BURN_KEY, burn);
export const loadBurn = () => read(BURN_KEY);

export const loadMissionForm = () => read(MISSION_KEY);
export const loadLead = () => read(PLAN_LEAD_KEY);
export const saveLead = (lead) => write(PLAN_LEAD_KEY, lead);
