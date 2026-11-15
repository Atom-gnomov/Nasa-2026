// Вступна заставка: відео логотипу (WebM з прозорістю) поверх затемненого зоряного простору; одразу після відблиску на ракеті —
// спалах, лого тане, інтерфейс і планети освітлюються. Раз за сесію; клік, Esc чи помилка відео одразу відкривають сайт.
// Відео стартує, коли небо під ним уже намальоване й не змінюється (sky-ready) і відео буферизоване, тож тло не блимає, а відтворення не смикається.
const root = document.documentElement;
const intro = document.getElementById("intro");
const anim = document.getElementById("intro-anim");
const FADE_MS = 1600;
const SKY_WAIT_MS = 4500; // скільки максимум чекаємо на небо й відео

function finish() {
  if (!root.classList.contains("intro-pending")) return;
  try { sessionStorage.setItem("lse-intro", "1"); } catch (_) { /* приватний режим — просто покажемо ще раз */ }
  root.classList.add("intro-reveal");
  root.classList.remove("intro-pending", "intro-playing");
  if (intro) intro.classList.add("is-leaving");
  window.setTimeout(() => {
    root.classList.remove("intro-reveal");
    intro?.remove();
  }, FADE_MS + 300);
}

// Підвантаження в кеш браузера (текстури, висоти, моделі, модулі інших сторінок): у фоні з низьким пріоритетом, коли сторінка вже
// завантажилась і браузер вільний, — щоб не гальмувати заставку й власні ресурси поточної сторінки. URL ті самі (?v=<версія з json>).
const page = document.body.className;
async function warmCache() {
  const quiet = (url, json = false) => fetch(url, json ? { cache: "no-cache" } : { priority: "low" })
    .then((r) => (r.ok ? (json ? r.json() : r.blob()) : null)).catch(() => null);
  const jobs = [];
  if (!page.includes("page-moon")) { // глобус: текстури, висоти, нахили
    const globe = await quiet("/assets/globe/globe.json", true);
    for (const f of [globe?.color?.file, globe?.height?.file, globe?.slope?.file]) {
      if (f) jobs.push(quiet(`/assets/globe/${f}?v=${globe.version ?? 0}`));
    }
  }
  if (!page.includes("page-system")) { // система: Земля, Сонце
    const system = await quiet("/assets/system/system.json", true);
    for (const a of Object.values(system?.assets ?? {})) {
      if (a?.file) jobs.push(quiet(`/assets/system/${a.file}?v=${system.version ?? 0}`));
    }
  }
  try {
    const map = JSON.parse(document.querySelector('script[type="importmap"]')?.textContent || "{}").imports || {};
    if (map.three) jobs.push(quiet(map.three));
  } catch (_) { /* без importmap — пропускаємо */ }
  for (const name of ["globe_view", "system_view", "surface_view", "regolith", "surface_terrain", "surface_geometry", "charts", "search"]) {
    jobs.push(quiet(`/static/js/${name}.js`));
  }
  await Promise.allSettled(jobs);
}
const idle = window.requestIdleCallback || ((fn) => window.setTimeout(fn, 800));
const warmLater = () => idle(warmCache);
if (document.readyState === "complete") warmLater(); else window.addEventListener("load", warmLater, { once: true });

if (!root.classList.contains("intro-pending") || !intro || !anim) {
  intro?.remove();
} else {
  let started = false, skyOk = !!window.__skyReady, videoOk = anim.readyState >= 3;
  const play = () => {
    if (started) return;
    started = true;
    root.classList.add("intro-playing"); // затемнення неба до 75 %
    window.setTimeout(finish, 4000);      // запасний вихід, якщо відео не завершилось
    anim.play().catch(finish);
  };
  const maybePlay = () => { if (skyOk && videoOk) play(); };
  anim.addEventListener("ended", finish); // відео обрізано одразу після відблиску: спалах, лого тане, інтерфейс освітлюється
  anim.addEventListener("error", finish);
  intro.addEventListener("click", finish);
  window.addEventListener("keydown", (e) => { if (e.key === "Escape" || e.key === " " || e.key === "Enter") finish(); }, { once: true });
  if (!videoOk) anim.addEventListener("canplaythrough", () => { videoOk = true; maybePlay(); }, { once: true });
  if (!skyOk) window.addEventListener("sky-ready", () => { skyOk = true; maybePlay(); }, { once: true });
  maybePlay();
  window.setTimeout(play, SKY_WAIT_MS); // запасний вихід, якщо щось не підготувалось
}
