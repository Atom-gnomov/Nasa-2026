// Модуль «Графіки таймлайну» (F5): кут Сонця й Землі над горизонтом і смуги видимості Сонця, Землі
// та зв'язку DSN за місячну добу від дати календаря — GET /api/timeline (ті самі параметри, що й підсумки
// «Період» в оверлеї). Малюється на canvas без бібліотек і збирача, у стилі добової кривої температури.
// Під курсором — момент і значення; висоти — над математичним горизонтом точки, видимість — над маскою
// рельєфу LOLA (horizon_source у відповіді).
import { SYNODIC_MONTH_DAYS } from "./calendar.js";
import { subscribe } from "./state.js";
import { onLangChange, t as tr } from "./i18n.js";

const HOUR_MS = 3_600_000;
export const PERIOD_H = SYNODIC_MONTH_DAYS * 24;

// Відповідь /api/timeline → ряди для графіка.
export function timelineSeries(t) {
  const n = t.times.length;
  const comm = Array.from({ length: n }, (_, i) => t.stations.filter((s) => s.available[i]).map((s) => s.station_id));
  return {
    t: t.times.map((s) => Date.parse(s)),
    sun: t.sun.elevation_deg,
    earth: t.earth.elevation_deg,
    sunVisible: t.sun.visible_fraction,
    earthVisible: t.earth.visible_fraction,
    comm, // id станцій DSN на зв'язку в кожен момент
  };
}

// Крок шкали кутів зі звичного ряду, щоб на шкалі було не більше ~5 поділок (±90° → 45°, ±7° → 5°).
const ANGLE_STEPS = [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 45, 90];
export function angleStep(span, ticks = 5) {
  const raw = Math.max(span, 1e-9) / ticks;
  return ANGLE_STEPS.find((s) => s >= raw) ?? 90;
}

// Межі осі кутів: охоплюють обидві криві й горизонт 0°, кратні кроку, не ширші за ±90°.
export function elevationRange(series) {
  const all = [...series.sun, ...series.earth, 0];
  const lo = Math.min(...all), hi = Math.max(...all);
  const step = angleStep(hi - lo || 1);
  return {
    min: Math.max(-90, Math.floor(lo / step) * step),
    max: Math.min(90, Math.ceil(hi / step) * step),
    step,
  };
}

// Поділки осі кутів: кратні кроку в межах [min, max].
export function angleTicks({ min, max, step }) {
  const out = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(+v.toFixed(6));
  return out;
}

// Індекси моментів для підписів дат: від початку ряду кожні 5 / 2 / 1 добу (за довжиною періоду).
export function dateTickIndices(series) {
  const n = series.t.length;
  if (n < 2) return [0];
  const spanDays = (series.t[n - 1] - series.t[0]) / (24 * HOUR_MS);
  const every = spanDays > 20 ? 5 : spanDays > 6 ? 2 : 1;
  const out = [];
  for (let d = 0; d <= spanDays + 1e-9; d += every) {
    const target = series.t[0] + d * 24 * HOUR_MS;
    let best = 0;
    for (let i = 1; i < n; i++) if (Math.abs(series.t[i] - target) < Math.abs(series.t[best] - target)) best = i;
    out.push(best);
  }
  return out;
}

// Найближчий момент ряду до частки ширини графіка (0…1).
export function indexAt(series, fraction) {
  const n = series.t.length;
  return Math.min(n - 1, Math.max(0, Math.round(fraction * (n - 1))));
}

const pad2 = (v) => String(v).padStart(2, "0");
const dayMonth = (ms) => { const d = new Date(ms); return `${pad2(d.getUTCDate())}.${pad2(d.getUTCMonth() + 1)}`; };
const stationName = (id) => id.charAt(0).toUpperCase() + id.slice(1);

export function readout(series, i) {
  const d = new Date(series.t[i]);
  const when = `${dayMonth(series.t[i])} ${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())} UTC`;
  const sun = `Сонце ${series.sun[i].toFixed(2)}° (видно ${Math.round(series.sunVisible[i] * 100)} %)`;
  const earth = `Земля ${series.earth[i].toFixed(2)}° (видно ${Math.round(series.earthVisible[i] * 100)} %)`;
  const dsn = series.comm[i].length ? `DSN: ${series.comm[i].map(stationName).join(", ")}` : "DSN: немає зв'язку";
  return `${when} · ${sun} · ${earth} · ${dsn}`;
}

// ---------- Малювання ----------
const BANDS = [
  { key: "sunVisible", label: "Сонце", color: [245, 185, 66] },
  { key: "earthVisible", label: "Земля", color: [90, 169, 255] },
  { key: "comm", label: "DSN", color: [143, 209, 143] },
];

export function drawTimeline(canvas, series, cursor = null) {
  const dpr = window.devicePixelRatio || 1;
  const w = Math.max(200, canvas.clientWidth), h = Math.max(160, canvas.clientHeight);
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);
  const g = canvas.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  const css = getComputedStyle(document.documentElement);
  const muted = css.getPropertyValue("--muted").trim() || "#8a92a6";
  const text = css.getPropertyValue("--text").trim() || "#e6e8ee";
  g.clearRect(0, 0, w, h);
  g.font = "11px system-ui";

  const bandH = 8, bandGap = 3;
  const pad = { l: 40, r: 8, t: 14, b: 20 + BANDS.length * (bandH + bandGap) };
  const plotB = h - pad.b;
  const range = elevationRange(series);
  const { min, max } = range;
  const n = series.t.length;
  const X = (i) => pad.l + (n > 1 ? i / (n - 1) : 0) * (w - pad.l - pad.r);
  const Y = (deg) => plotB - ((deg - min) / (max - min || 1)) * (plotB - pad.t);

  // Сітка й підписи кутів
  g.strokeStyle = "rgba(138,146,166,0.25)";
  g.fillStyle = muted;
  for (const v of angleTicks(range)) {
    g.beginPath(); g.moveTo(pad.l, Y(v)); g.lineTo(w - pad.r, Y(v)); g.stroke();
    g.fillText(`${v}°`, 2, Y(v) + 4);
  }
  // Горизонт 0°
  g.strokeStyle = "rgba(230,232,238,0.55)"; g.setLineDash([4, 4]);
  g.beginPath(); g.moveTo(pad.l, Y(0)); g.lineTo(w - pad.r, Y(0)); g.stroke(); g.setLineDash([]);

  // Підписи дат: кожні 5 діб (місячна доба), 2 або 1 добу для коротших періодів
  g.fillStyle = muted;
  for (const i of dateTickIndices(series)) g.fillText(dayMonth(series.t[i]), Math.min(X(i) - 12, w - 34), h - 5);

  // Криві: Сонце й Земля
  for (const [key, color] of [["sun", "rgb(245,185,66)"], ["earth", "rgb(90,169,255)"]]) {
    g.strokeStyle = color; g.lineWidth = 1.6; g.beginPath();
    series[key].forEach((v, i) => (i ? g.lineTo(X(i), Y(v)) : g.moveTo(X(i), Y(v))));
    g.stroke();
  }
  g.lineWidth = 1;
  g.fillStyle = "rgb(245,185,66)"; g.fillText(`— ${tr("Сонце")}`, pad.l + 4, 11);
  g.fillStyle = "rgb(90,169,255)"; g.fillText(`— ${tr("Земля")}`, pad.l + 60, 11);

  // Смуги видимості: яскравість = частка диска над маскою; DSN — хоча б одна станція
  BANDS.forEach((b, k) => {
    const y = plotB + 6 + k * (bandH + bandGap);
    g.fillStyle = muted; g.fillText(tr(b.label), 2, y + bandH);
    for (let i = 0; i < n - 1; i++) {
      const v = b.key === "comm" ? (series.comm[i].length ? 1 : 0) : series[b.key][i];
      if (v <= 0) continue;
      g.fillStyle = `rgba(${b.color.join(",")},${0.25 + 0.75 * v})`;
      g.fillRect(X(i), y, Math.max(1, X(i + 1) - X(i)), bandH);
    }
  });

  if (cursor !== null) {
    g.strokeStyle = text; g.globalAlpha = 0.6;
    g.beginPath(); g.moveTo(X(cursor), pad.t); g.lineTo(X(cursor), h - 18); g.stroke();
    g.globalAlpha = 1;
  }
  return { left: pad.l, right: w - pad.r };
}

// ---------- Панель на сторінці «Місяць» ----------
const canvas = typeof document === "undefined" ? null : document.getElementById("timeline-chart");
if (canvas) {
  const summary = document.getElementById("timeline-summary");
  const out = document.getElementById("timeline-readout");
  let series = null, frame = null, key = null, abort = null, timer = null, lastSummary = null;
  // Підсумок — речення-шаблон з підстановкою (перекладається разом з мовою)
  function renderSummary() {
    if (!lastSummary) return;
    const terrain = lastSummary.source === "flat" ? tr("гладка сфера") : `LOLA ${lastSummary.source.toUpperCase()}`;
    summary.textContent = tr("Від {from} на 29,53 доби: Сонце {sun} % часу, зв'язок DSN {comm} %. Рельєф: {terrain}.", { ...lastSummary, terrain });
  }
  const redraw = (cursor = null) => { if (series) frame = drawTimeline(canvas, series, cursor); };

  async function load({ lat, lon, datetime }) {
    if (lat == null || lon == null) {
      series = null; key = null;
      canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
      summary.textContent = "Виберіть місце на Місяці";
      out.textContent = "";
      return;
    }
    const k = `${lat}|${lon}|${datetime}`;
    if (k === key) return;
    key = k;
    abort?.abort();
    abort = new AbortController();
    const start = Date.parse(datetime);
    const end = new Date(start + PERIOD_H * HOUR_MS).toISOString().slice(0, 16) + "Z";
    summary.textContent = "Рахую…";
    try {
      const res = await fetch(`/api/timeline?${new URLSearchParams({ lat, lon, start: datetime, end, step_h: 1 })}`, { signal: abort.signal });
      const t = await res.json();
      if (!res.ok) throw new Error(t.detail || res.statusText);
      series = timelineSeries(t);
      redraw();
      const s = t.summary;
      lastSummary = { from: dayMonth(series.t[0]), sun: Math.round(s.sun_fraction * 100), comm: Math.round(s.comm_fraction * 100), source: t.horizon_source };
      renderSummary();
      out.textContent = "Наведіть курсор на графік — момент і значення.";
    } catch (err) {
      if (err.name === "AbortError") return;
      key = null;
      summary.textContent = `Таймлайн недоступний: ${err.message}`;
    }
  }

  canvas.addEventListener("mousemove", (ev) => {
    if (!series || !frame) return;
    const r = canvas.getBoundingClientRect();
    const i = indexAt(series, (ev.clientX - r.left - frame.left) / (frame.right - frame.left));
    redraw(i);
    out.textContent = readout(series, i);
  });
  canvas.addEventListener("mouseleave", () => redraw());
  new ResizeObserver(() => redraw()).observe(canvas);
  subscribe((st) => { clearTimeout(timer); timer = setTimeout(() => load(st), 300); });
  onLangChange(() => { renderSummary(); redraw(); });
}
