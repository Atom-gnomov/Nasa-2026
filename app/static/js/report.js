// Крок 10 «Підсумковий звіт» (F29, П-14): вибори майстра → POST /api/report (B24) → звіт за кроками, схема рішень,
// друк/PDF, Markdown, JSON. Чисті функції — без DOM, тестуються в Node (tests/js/test_report.mjs).
import { t, onLangChange } from "./i18n.js";
import { getState, subscribe } from "./state.js";
import { buildConsistencyRequest } from "./consistency.js";
import { loadLaunch } from "./pipeline.js";
import { loadLead, loadMissionForm } from "./selection.js";
import { STEPS, loadPlan, stepHref } from "./mission_plan.js";

// Тіло POST /api/report: як для перевірки, плюс назва вибраного місця (лише для звіту).
export function buildReportRequest(ctx) {
  const body = buildConsistencyRequest(ctx);
  const name = ctx.siteName;
  if (body.site && name) body.site = { ...body.site, name };
  return body;
}

// Ім'я файлу з назви місії: літери й цифри через дефіс, інакше «mission».
export function fileName(name, ext) {
  const slug = String(name ?? "").trim().toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-+|-+$/g, "");
  return `${slug || "mission"}.${ext}`;
}

// Що віддаємо на завантаження: текст і тип для Markdown та JSON.
export function downloadParts(rep, kind) {
  if (kind === "json") return { text: JSON.stringify(rep, null, 2), type: "application/json;charset=utf-8", name: fileName(rep.name, "json") };
  return { text: rep.markdown, type: "text/markdown;charset=utf-8", name: fileName(rep.name, "md") };
}

// Крок звіту → адреса в майстрі, щоб повернутися й виправити (null — кроку немає).
export function stepLink(n, search = "") {
  const step = STEPS.find((s) => s.n === n && s.ready);
  return step ? stepHref(step, search) : null;
}

export const verdictText = (rep) => (rep.ok ? t("Конфліктів, що блокують місію, немає.") : t("Є конфлікти, що блокують місію: виправте їх на вказаних кроках."));

// ---------- DOM ----------
if (typeof document !== "undefined" && document.getElementById("r-body")) {
  const $ = (id) => document.getElementById(id);
  const el = (tag, props = {}, ...kids) => { const n = Object.assign(document.createElement(tag), props); n.append(...kids); return n; };
  let timer = null;
  let abort = null;
  let last = null;
  let siteNames = null;
  const DEBOUNCE_MS = 300;

  function render() {
    const body = $("r-body");
    if (!last) { body.replaceChildren(); return; }
    const nodes = [el("h3", { textContent: `${t("Місія")}: ${last.name || t("без назви")}` }),
      el("p", { className: "check-summary", textContent: verdictText(last) })];
    nodes[1].dataset.ok = String(last.ok);
    for (const sec of last.sections) {
      const link = stepLink(sec.step, location.search);
      const head = el("h4", {}, `${sec.step}. ${sec.title} `);
      if (link) head.append(el("a", { href: link, className: "no-print", textContent: t("змінити"), title: t("Повернутися до кроку {n}", { n: sec.step }) }));
      nodes.push(head, el("dl", { className: "report-dl" }, ...sec.rows.flatMap((r) => [el("dt", { textContent: r.label }), el("dd", { textContent: r.value })])));
    }
    nodes.push(el("h4", { textContent: t("Послідовність рішень") }),
      el("p", { className: "report-chain", textContent: last.chain.join(" → ") }));
    if (last.sources.length) {
      nodes.push(el("h4", { textContent: t("Джерела") }),
        el("ul", {}, ...last.sources.map((s) => el("li", {}, `${s.title}${s.ref ? `, ${s.ref}` : ""} — `, el("a", { href: s.url, target: "_blank", rel: "noopener", textContent: s.url })))));
    }
    nodes.push(...last.caveats.map((c) => el("p", { className: "muted small", textContent: `⚠️ ${c}` })));
    body.replaceChildren(...nodes);
  }

  async function siteName(st) {
    if (!st.site) return null;
    try {
      siteNames ??= await fetch("/api/sites").then((r) => r.json());
      return siteNames.find((x) => x.id === st.site)?.name ?? null;
    } catch { return null; }
  }

  async function run() {
    abort?.abort();
    abort = new AbortController();
    try {
      const st = getState();
      const body = buildReportRequest({ missionRaw: loadMissionForm(), launch: loadLaunch(), lead: loadLead(), state: st, plan: loadPlan(), siteName: await siteName(st) });
      const res = await fetch("/api/report", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: abort.signal });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      last = data;
      $("r-status").hidden = true;
    } catch (err) {
      if (err.name === "AbortError") return;
      $("r-status").textContent = err.message;
      $("r-status").hidden = false;
    }
    render();
  }
  const schedule = () => { clearTimeout(timer); timer = setTimeout(run, DEBOUNCE_MS); };

  function save(kind) {
    if (!last) return;
    const part = downloadParts(last, kind);
    const a = el("a", { href: URL.createObjectURL(new Blob([part.text], { type: part.type })), download: part.name });
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
  $("r-print").addEventListener("click", () => window.print());
  $("r-md").addEventListener("click", () => save("md"));
  $("r-json").addEventListener("click", () => save("json"));
  $("r-copy").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(last?.markdown ?? ""); $("r-note").textContent = t("Скопійовано."); }
    catch { $("r-note").textContent = t("Не вдалося скопіювати: скористайтеся «Завантажити Markdown»."); }
  });
  subscribe(schedule);
  window.addEventListener("storage", schedule);
  window.addEventListener("pageshow", schedule);
  onLangChange(render);
}
