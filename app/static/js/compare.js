// Модуль «Порівняння» (М14): два місця каталогу поруч на дату зі спільного стану — GET /api/compare.
// Вибір зберігається в стані як compare: [id, id] (CONTRACTS.md §5.1), тож потрапляє в посилання.
// У кожному рядку виділено краще значення для посадкового апарата на сонячних панелях
// зі зв'язком через DSN; правило — поле better у ROWS ("max" | "min" | null — довідковий рядок).
// Значення порівнюються з тією ж точністю, з якою показуються (CONTRACTS.md §5.3), тож різниця,
// невидима на екрані, не виділяється.
import { setState, subscribe } from "./state.js";

const round = (v, d) => (v == null ? null : Math.round(v * 10 ** d) / 10 ** d);
const roundOrInf = (v, d) => (v == null ? Infinity : round(v, d)); // null у hours_to_* — події немає у вікні пошуку
const deg = (v) => (v == null ? "—" : `${v.toFixed(2)}°`);
const pct = (v) => (v == null ? "—" : `${Math.round(v * 100)} %`);
const watts = (v) => (v == null ? "—" : `${v.toFixed(0)} Вт`);
const hours = (v, m) => {
  if (v == null) return `немає за ${Math.round(m.event_search_hours / 24)} діб`;
  return v >= 48 ? `${v.toFixed(0)} год (${(v / 24).toFixed(1)} доби)` : `${v.toFixed(1)} год`;
};
const clock = (h) => {
  if (h == null) return "—";
  const min = Math.round(h * 60) % 1440;
  return `${String(Math.floor(min / 60)).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}`;
};
const sunUp = (m) => m.sun_visible_fraction > 0;
const available = (m) => (m.stations ?? []).filter((s) => s.available);

export const ROWS = [
  { label: "Сонце видно", text: (m) => pct(m.sun_visible_fraction), num: (m) => round(m.sun_visible_fraction, 2), better: "max" },
  { label: "Кут Сонця", text: (m) => deg(m.sun_elevation_deg), better: null },
  // Події порівнюються, лише коли обидва місця в однаковому стані: hours_to_sunrise для освітленого
  // місця — це схід після наступного заходу, тож порівнювати його з тінню некоректно.
  { label: "До заходу Сонця", text: (m) => hours(m.hours_to_sunset, m), num: (m) => roundOrInf(m.hours_to_sunset, 1), better: "max", when: (a, b) => sunUp(a) && sunUp(b) },
  { label: "До сходу Сонця", text: (m) => hours(m.hours_to_sunrise, m), num: (m) => roundOrInf(m.hours_to_sunrise, 1), better: "min", when: (a, b) => !sunUp(a) && !sunUp(b) },
  { label: "Панель 1 м² вертикальна", text: (m) => watts(m.panel_power_vertical_w_m2), num: (m) => round(m.panel_power_vertical_w_m2, 0), better: "max" },
  { label: "Панель 1 м² горизонтальна", text: (m) => watts(m.panel_power_horizontal_w_m2), num: (m) => round(m.panel_power_horizontal_w_m2, 0), better: "max" },
  { label: "Земля видна", text: (m) => (m.earth_visible ? `так (${pct(m.earth_visible_fraction)} диска)` : "ні"), num: (m) => round(m.earth_visible_fraction, 2), better: "max" },
  { label: "Кут Землі", text: (m) => deg(m.earth_elevation_deg), better: null },
  { label: "До заходу Землі", text: (m) => hours(m.hours_to_earthset, m), num: (m) => roundOrInf(m.hours_to_earthset, 1), better: "max", when: (a, b) => a.earth_visible && b.earth_visible },
  { label: "До сходу Землі", text: (m) => hours(m.hours_to_earthrise, m), num: (m) => roundOrInf(m.hours_to_earthrise, 1), better: "min", when: (a, b) => !a.earth_visible && !b.earth_visible },
  {
    label: "Станцій DSN на зв'язку",
    text: (m) => {
      const best = (m.stations ?? []).find((s) => s.id === m.recommended_station);
      return `${available(m).length} з ${(m.stations ?? []).length}${best ? ` · ${best.name.split(" (")[0]}` : ""}`;
    },
    num: (m) => available(m).length,
    better: "max",
  },
  // Без станції затримка рахується до центру Землі — порівнюємо лише коли зв'язок є в обох.
  { label: "Затримка сигналу", text: (m) => `${m.signal_delay_s.toFixed(3)} с`, num: (m) => round(m.signal_delay_s, 3), better: "min", when: (a, b) => a.recommended_station != null && b.recommended_station != null },
  { label: "Місцевий сонячний час", text: (m) => clock(m.local_solar_time_h), better: null },
  { label: "Маска горизонту", text: (m) => (m.horizon_source === "flat" ? "гладка сфера" : `LOLA ${String(m.horizon_source).toUpperCase()}`), better: null },
];

// Яке значення в рядку краще: "a", "b" або null (рядок довідковий, умова не виконана, значення рівні).
export function pickBetter(row, ma, mb) {
  if (!row.better || !row.num || (row.when && !row.when(ma, mb))) return null;
  const a = row.num(ma);
  const b = row.num(mb);
  if (a == null || b == null || Number.isNaN(a) || Number.isNaN(b) || a === b) return null;
  return (row.better === "max") === (a > b) ? "a" : "b";
}

// Рядки таблиці для двох відповідей /api/compare.
export function tableRows(ma, mb) {
  return ROWS.map((row) => ({ label: row.label, a: row.text(ma), b: row.text(mb), better: pickBetter(row, ma, mb) }));
}

export function compareUrl(ids, datetime) {
  const params = new URLSearchParams(ids.map((id) => ["site", id]));
  if (datetime) params.set("datetime", datetime);
  return `/api/compare?${params}`;
}

// ---------- Інтерфейс (панель «Порівняння» у moon.html) ----------
const root = typeof document === "undefined" ? null : document.getElementById("compare");
if (root) {
  const selects = [root.querySelector("#compare-a"), root.querySelector("#compare-b")];
  const status = root.querySelector("#compare-status");
  const table = root.querySelector("#compare-table");
  let abort = null;
  let timer = null;
  let lastKey = "";

  const showStatus = (text) => { status.textContent = text; status.hidden = !text; };

  function render(items) {
    const [a, b] = items;
    const head = table.tHead.rows[0].cells;
    for (const [i, item] of [[1, a], [2, b]]) {
      head[i].replaceChildren();
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "linklike";
      btn.textContent = item.site.name;
      btn.title = "Показати це місце на глобусі й в оверлеї";
      btn.addEventListener("click", () => setState({ site: item.site.name, lat: item.site.lat, lon: item.site.lon }));
      head[i].append(btn);
    }
    const body = table.tBodies[0];
    body.replaceChildren();
    for (const row of tableRows(a.metrics, b.metrics)) {
      const tr = body.insertRow();
      const th = document.createElement("th");
      th.scope = "row";
      th.textContent = row.label;
      tr.append(th);
      for (const side of ["a", "b"]) {
        const td = tr.insertCell();
        td.textContent = row[side];
        if (row.better === side) { td.className = "better"; td.title = "Краще значення"; }
      }
    }
    table.hidden = false;
  }

  async function load(ids, datetime) {
    abort?.abort();
    abort = new AbortController();
    showStatus("Рахую…");
    try {
      const res = await fetch(compareUrl(ids, datetime), { signal: abort.signal });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || res.statusText);
      render(body);
      showStatus("");
    } catch (err) {
      if (err.name === "AbortError") return;
      table.hidden = true;
      showStatus(err.message);
    }
  }

  function update({ compare, datetime }) {
    const ids = (compare ?? []).slice(0, 2);
    selects.forEach((sel, i) => { if (sel.options.length > 1) sel.value = ids[i] ?? ""; });
    const key = `${ids.join(",")}|${datetime}`;
    if (key === lastKey) return;
    lastKey = key;
    clearTimeout(timer);
    abort?.abort();
    if (ids.length < 2 || !ids[0] || !ids[1]) { table.hidden = true; showStatus("Виберіть два місця зі списку"); return; }
    if (ids[0] === ids[1]) { table.hidden = true; showStatus("Виберіть два різні місця"); return; }
    timer = setTimeout(() => load(ids, datetime), 200); // debounce: кроки календаря й швидке перемикання
  }

  for (const sel of selects) {
    sel.addEventListener("change", () => setState({ compare: selects.map((el) => el.value).filter(Boolean) }));
  }

  (async () => {
    try {
      const res = await fetch("/api/sites");
      const sites = await res.json();
      if (!res.ok) throw new Error(sites.detail || res.statusText);
      for (const sel of selects) {
        for (const site of sites) sel.append(new Option(site.name, site.id));
      }
    } catch (err) {
      showStatus(`Список місць: ${err.message}`);
    }
    lastKey = "";
    subscribe(update); // викликає update одразу з поточним станом
  })();
}
