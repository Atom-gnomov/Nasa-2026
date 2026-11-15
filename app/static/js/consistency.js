// Крок 9 «Перевірка узгодженості» (F28, П-14): вибори майстра зі спільних сховищ → POST /api/consistency (B23) →
// список конфліктів із кнопкою «Перейти до кроку N». Запускається сама після кожної зміни виборів.
// Чисті функції — без DOM, тестуються в Node (tests/js/test_consistency.mjs).
import { t, onLangChange } from "./i18n.js";
import { getState, subscribe } from "./state.js";
import { buildMissionRequest, normalizeForm } from "./mission.js";
import { DEFAULT_LAUNCH, effectiveSite, effectiveTrajectory, loadLaunch, plainSite, stayDays } from "./pipeline.js";
import { loadLead, loadMissionForm, MISSION_KEY } from "./selection.js";
import { STEPS, loadPlan, stepHref } from "./mission_plan.js";

export const SEVERITY_ICON = { error: "✗", warning: "!", info: "·" };
export const SEVERITY_LABEL = { error: "Місія не виконується", warning: "Варто виправити", info: "Зауваження" };

// Тіло POST /api/consistency зі спільних сховищ: форма «Місії», вибір польоту, дата й точка зі стану, назва й мета.
export function buildConsistencyRequest(ctx) {
  const { missionRaw = null, lead = null, state = {}, plan = {} } = ctx;
  const launch = { ...DEFAULT_LAUNCH, ...ctx.launch };
  const form = normalizeForm(missionRaw);
  const mission = buildMissionRequest(form);
  const site = plainSite(effectiveSite(launch, lead));
  mission.trajectory = effectiveTrajectory(launch, lead);
  if (launch.vehicle && launch.vehicle !== "any") mission.launch_system_id = launch.vehicle;
  if (site) mission.launch_site_id = site;
  const body = { mission, stay_days: form.crewed ? form.days : stayDays(missionRaw) };
  if (state.datetime) body.datetime = state.datetime;
  body.site = state.lat != null && state.lon != null ? { lat: state.lat, lon: state.lon } : null;
  if (plan.goal) body.goal = plan.goal;
  if (plan.name) body.name = plan.name;
  return body;
}

// Підсумок: «2 — місія не виконується; 1 — варто виправити…» або «Суперечностей не знайдено».
export function summaryText(resp) {
  if (!resp) return "";
  const c = resp.counts;
  if (!c.error && !c.warning && !c.info) return t("Суперечностей між виборами не знайдено.");
  const parts = [];
  if (c.error) parts.push(t("{n} — місія не виконується", { n: c.error }));
  if (c.warning) parts.push(t("{n} — варто виправити", { n: c.warning }));
  if (c.info) parts.push(t("{n} — зауваження", { n: c.info }));
  return parts.join("; ");
}

// Рядки списку: серйозність, значок, текст і крок, де це виправити (назва кроку — як у майстрі).
export function conflictRows(resp) {
  return (resp?.conflicts ?? []).map((c) => ({
    severity: c.severity, icon: SEVERITY_ICON[c.severity] ?? "·", message: c.message, step: c.step,
    stepTitle: STEPS.find((s) => s.n === c.step)?.title ?? "",
  }));
}

export function windowText(w) {
  if (!w) return "";
  const fmt = (x) => x.replace("T", " ").replace("Z", " UTC");
  const parts = [`${fmt(w.start)} — ${fmt(w.end)}`];
  if (w.sun_fraction != null) parts.push(t("Сонце над горизонтом {p} % часу", { p: Math.round(w.sun_fraction * 100) }));
  if (w.earth_fraction != null) parts.push(t("Земля над горизонтом {p} % часу", { p: Math.round(w.earth_fraction * 100) }));
  if (w.longest_night_h != null) parts.push(t("найдовша ніч {h} год", { h: Math.round(w.longest_night_h) }));
  return parts.join(" · ");
}

// Форма «Місії» з урахованою найдовшою ніччю (поле nightH) — підказка перевірки.
export function withNight(missionRaw, hours) {
  return { ...(missionRaw ?? {}), nightH: hours };
}

// ---------- DOM ----------
if (typeof document !== "undefined" && document.getElementById("c-list")) {
  const $ = (id) => document.getElementById(id);
  let timer = null;
  let abort = null;
  let last = null;
  const DEBOUNCE_MS = 300;

  function render() {
    $("c-summary").textContent = summaryText(last);
    $("c-summary").dataset.ok = last ? String(last.ok) : "";
    $("c-list").replaceChildren(...conflictRows(last).map((r) => {
      const li = Object.assign(document.createElement("li"), { className: `check-${r.severity}` });
      li.append(Object.assign(document.createElement("span"), { className: "check-mark", textContent: r.icon, title: t(SEVERITY_LABEL[r.severity]) }),
        Object.assign(document.createElement("span"), { textContent: r.message }));
      const step = STEPS.find((s) => s.n === r.step);
      if (step) li.append(Object.assign(document.createElement("a"), { className: "button", href: stepHref(step, location.search), textContent: t("До кроку {n}", { n: r.step }), title: t(r.stepTitle) }));
      return li;
    }));
    const night = last?.suggested?.longest_night_h;
    $("c-night").hidden = night == null;
    if (night != null) $("c-night").textContent = t("Врахувати найдовшу ніч ({h} год) у розрахунку акумуляторів", { h: Math.round(night) });
    $("c-window-box").hidden = !last?.window;
    $("c-window").textContent = windowText(last?.window);
    $("c-skipped-box").hidden = !last?.skipped?.length;
    $("c-skipped").replaceChildren(...(last?.skipped ?? []).map((s) => Object.assign(document.createElement("li"), { textContent: s.reason })));
  }

  async function run() {
    abort?.abort();
    abort = new AbortController();
    try {
      const body = buildConsistencyRequest({ missionRaw: loadMissionForm(), launch: loadLaunch(), lead: loadLead(), state: getState(), plan: loadPlan() });
      const res = await fetch("/api/consistency", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: abort.signal });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      last = data;
      $("c-status").hidden = true;
    } catch (err) {
      if (err.name === "AbortError") return;
      $("c-status").textContent = err.message;
      $("c-status").hidden = false;
    }
    render();
  }
  const schedule = () => { clearTimeout(timer); timer = setTimeout(run, DEBOUNCE_MS); };
  $("c-night").addEventListener("click", () => {
    const hours = last?.suggested?.longest_night_h;
    if (hours == null) return;
    try { localStorage.setItem(MISSION_KEY, JSON.stringify(withNight(loadMissionForm(), hours))); } catch { /* приватний режим */ }
    schedule();
  });
  subscribe(schedule);
  window.addEventListener("storage", schedule);
  window.addEventListener("pageshow", schedule);
  onLangChange(render);
}
