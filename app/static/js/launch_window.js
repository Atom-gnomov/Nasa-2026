// Вкладка «Вікно запуску» (F7): шкала дат старту з оцінкою у %, найкраща дата виділена — GET /api/launch-window (B8).
// Точка посадки й початок періоду — зі спільного стану (вибір на вкладці «Місяць», календар); клік по даті
// переносить її в календар. Чисті функції експортуються для тестів у Node (tests/js/test_launch_window.mjs).
import { getState, setState, subscribe } from "./state.js";

export const FACTORS = ["light", "fuel", "comms", "windows"];
export const FACTOR_LABELS = {
  light: "Світло після посадки",
  fuel: "Паливо (Δv)",
  comms: "Зв'язок із Землею",
  windows: "Вікна запуску на добу",
};
const MAX_DAYS = 60;

const pct = (v) => (v == null ? "—" : `${Math.round(v * 100)} %`);
const pad = (n) => String(n).padStart(2, "0");

// "YYYY-MM-DD" + n діб → "YYYY-MM-DD" (UTC, без переходів на літній час)
export function addDays(isoDate, n) {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

// Запит до /api/launch-window з вибору користувача й спільного стану; null — бракує точки чи майданчика.
export function launchWindowUrl({ siteId, lat, lon, datetime, days = 30, trajectory = "direct", priorities = FACTORS }) {
  if (!siteId || lat == null || lon == null || !datetime) return null;
  const n = Math.min(Math.max(Math.round(Number(days)) || 1, 1), MAX_DAYS);
  const start = String(datetime).slice(0, 10);
  const params = new URLSearchParams({
    launch_site: siteId, lat: String(lat), lon: String(lon),
    start, end: addDays(start, n - 1), trajectory, priorities: priorities.join(","),
  });
  return `/api/launch-window?${params}`;
}

// Переставляє фактор i на одну позицію вгору (dir = −1) чи вниз (+1); повертає новий масив.
export function movePriority(list, i, dir) {
  const j = i + dir;
  if (i < 0 || i >= list.length || j < 0 || j >= list.length) return list.slice();
  const out = list.slice();
  [out[i], out[j]] = [out[j], out[i]];
  return out;
}

const shortDate = (iso) => `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;
const arrivalText = (iso) => (iso ? `${shortDate(iso.slice(0, 10))} ${iso.slice(11, 16)}` : "—");

// Стовпчики шкали: дата, оцінка, найкраща, підказка з факторами.
export function scaleItems(win) {
  const best = win?.best?.date;
  return (win?.days ?? []).map((d) => ({
    date: d.date,
    label: shortDate(d.date),
    pct: Math.max(0, Math.min(100, d.score_pct)),
    best: d.date === best,
    sunlit: Boolean(d.sunlit_at_arrival),
    title: [
      `${d.date}: ${d.score_pct.toFixed(1)} %`,
      ...Object.entries(d.factors ?? {}).map(([k, v]) => `${FACTOR_LABELS[k] ?? k}: ${pct(v)}`),
      `Прибуття: ${arrivalText(d.arrival)} UTC`,
    ].join("\n"),
  }));
}

// Рядки таблиці під шкалою (усі значення — текст, без undefined/NaN).
export function tableRows(win) {
  const best = win?.best?.date;
  return (win?.days ?? []).map((d) => ({
    date: d.date,
    best: d.date === best,
    cells: [
      d.date,
      `${d.score_pct.toFixed(1)} %`,
      arrivalText(d.arrival),
      d.dv_total_m_s == null ? "—" : Math.round(d.dv_total_m_s).toLocaleString("uk-UA"),
      d.windows_per_day == null ? "—" : String(d.windows_per_day),
      `${pct(d.sun_fraction)}${d.sunlit_at_arrival ? " · світло при посадці" : ""}`,
      pct(d.earth_fraction),
    ],
  }));
}

export function bestText(win, siteName = win?.launch_site_id) {
  if (!win?.best) return "";
  const day = (win.days ?? []).find((d) => d.date === win.best.date);
  const method = win.method === "estimate" ? " Економна траєкторія — оцінка." : "";
  const arrival = day ? `, прибуття ${arrivalText(day.arrival)} UTC` : "";
  return `Найкраща дата старту з «${siteName}»: ${win.best.date} — ${win.best.score_pct.toFixed(1)} %${arrival}.${method}`;
}

// Дата шкали → значення календаря (старт о 00:00 UTC, як у розрахунку).
export const calendarDatetime = (isoDate) => `${isoDate}T00:00Z`;

// --- DOM ------------------------------------------------------------------------------------------------------

function init() {
  const $ = (id) => document.getElementById(id);
  const form = $("lw-form");
  if (!form) return;
  const siteSel = $("lw-site");
  const status = $("lw-status");
  const scale = $("lw-scale");
  const bestEl = $("lw-best");
  const table = $("lw-table");
  const pointEl = $("lw-point");
  const prioEl = $("lw-priorities");
  let priorities = FACTORS.slice();
  let controller = null;
  let sites = [];

  const renderPriorities = () => {
    prioEl.replaceChildren(...priorities.map((f, i) => {
      const li = document.createElement("li");
      li.textContent = FACTOR_LABELS[f];
      for (const [dir, text, label] of [[-1, "↑", "вище"], [1, "↓", "нижче"]]) {
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = text;
        b.title = `${FACTOR_LABELS[f]} — ${label}`;
        b.disabled = (dir < 0 && i === 0) || (dir > 0 && i === priorities.length - 1);
        b.addEventListener("click", () => { priorities = movePriority(priorities, i, dir); renderPriorities(); });
        li.append(" ", b);
      }
      return li;
    }));
  };

  const renderPoint = (s) => {
    pointEl.textContent = s.lat == null || s.lon == null
      ? "не вибрано — виберіть її на вкладці «Місяць»"
      : `${s.site ? `${s.site} · ` : ""}${s.lat.toFixed(2)}°, ${s.lon.toFixed(2)}°`;
  };

  const render = (win) => {
    scale.replaceChildren(...scaleItems(win).map((it) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = `lw-bar${it.best ? " best" : ""}${it.sunlit ? " sunlit" : ""}`;
      b.setAttribute("role", "listitem");
      b.style.setProperty("--h", `${it.pct}%`);
      b.title = it.title;
      b.innerHTML = `<span class="lw-fill"></span><span class="lw-pct">${Math.round(it.pct)}</span><span class="lw-date">${it.label}</span>`;
      b.addEventListener("click", () => setState({ datetime: calendarDatetime(it.date) }));
      return b;
    }));
    const siteName = sites.find((s) => s.id === win.launch_site_id)?.name ?? win.launch_site_id;
    bestEl.textContent = bestText(win, siteName);
    bestEl.hidden = false;
    table.tBodies[0].replaceChildren(...tableRows(win).map((r) => {
      const tr = document.createElement("tr");
      if (r.best) tr.className = "best";
      for (const c of r.cells) {
        const td = document.createElement("td");
        td.textContent = c;
        tr.append(td);
      }
      const td = document.createElement("td");
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = "У календар";
      b.addEventListener("click", () => setState({ datetime: calendarDatetime(r.date) }));
      td.append(b);
      tr.append(td);
      return tr;
    }));
    table.hidden = false;
  };

  const run = async () => {
    const s = getState();
    const url = launchWindowUrl({
      siteId: siteSel.value, lat: s.lat, lon: s.lon, datetime: s.datetime,
      days: $("lw-days").value, trajectory: $("lw-trajectory").value, priorities,
    });
    if (!url) {
      status.textContent = "Виберіть точку посадки на вкладці «Місяць» і майданчик старту.";
      return;
    }
    controller?.abort();
    controller = new AbortController();
    status.textContent = "Рахую вікно запуску…";
    $("lw-run").disabled = true;
    try {
      const res = await fetch(url, { signal: controller.signal });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail ?? `HTTP ${res.status}`);
      status.textContent = body.horizon_source === "flat"
        ? "Горизонт точки — гладка сфера (рельєфу LOLA для неї немає)."
        : "";
      render(body);
    } catch (err) {
      if (err.name !== "AbortError") status.textContent = `Помилка: ${err.message}`;
    } finally {
      $("lw-run").disabled = false;
    }
  };

  form.addEventListener("submit", (e) => { e.preventDefault(); run(); });
  renderPriorities();
  renderPoint(getState());
  subscribe(renderPoint);
  fetch("/api/launch-sites").then((r) => r.json()).then((list) => {
    sites = list;
    siteSel.replaceChildren(...list.map((s) => new Option(`${s.name} (${s.lat.toFixed(1)}°)`, s.id)));
  }).catch(() => { status.textContent = "Не вдалося завантажити каталог майданчиків."; });
}

if (typeof document !== "undefined") init();
