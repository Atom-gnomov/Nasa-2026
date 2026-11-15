// Екран завантаження: логотип крутиться, смуга показує готовність даних NASA (/api/data/status), поки сторінка не завантажилась і
// застосунок не підготував дані. Краще чекати довго, ніж відкрити недозавантажений сайт: екран сам не закривається при збої чи
// затримці, а дає кнопки «Спробувати знову» й «Відкрити як є». Логіка стану — чиста функція (тестується в Node); DOM — лише в браузері.

const POLL_MS = 1500;
const START_GRACE_POLLS = 4;   // стільки опитувань даємо підготовці на старт (набір ще «missing», але автозапуск увімкнено)
const SKY_WAIT_MS = 10000;     // небо чекаємо не довше (без нього сторінка працює)
const STUCK_MS = 20 * 60000;   // після цього — кнопки замість нескінченного очікування

// Відповідь /api/data/status → { kind: "wait" | "failed" | "ready", progress: 0..1, text } для екрана завантаження.
export function loaderState(status, polls = 0) {
  const sets = status?.datasets ?? [];
  const total = sets.length || 1;
  const progress = sets.filter((d) => d.state === "ready").length / total;
  const running = sets.filter((d) => d.state === "running");
  const starting = Boolean(status?.auto_prepare) && polls < START_GRACE_POLLS && sets.some((d) => d.state === "missing");
  if (running.length || starting) {
    const first = running[0];
    return { kind: "wait", progress, text: first ? `${first.label}${first.message ? ` — ${first.message}` : ""}` : "" };
  }
  const failed = sets.find((d) => d.state === "failed");
  if (failed) return { kind: "failed", progress, text: `${failed.label}: ${failed.message ?? ""}`.trim() };
  return { kind: "ready", progress: 1, text: "" };
}

if (typeof document !== "undefined") {
  const root = document.documentElement;
  const el = document.getElementById("boot-loader");
  if (!el) {
    root.classList.remove("boot-loading");
  } else {
    const bar = el.querySelector(".boot-bar span");
    const text = el.querySelector(".boot-text");
    const actions = el.querySelector(".boot-actions");
    const t0 = performance.now();
    const sleep = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));
    let skipped = false;
    const close = () => {
      root.classList.remove("boot-loading");
      el.classList.add("is-done");
      window.setTimeout(() => el.remove(), 500);
    };
    const show = (state) => {
      el.classList.toggle("is-indeterminate", state.kind === "wait" && state.progress === 0);
      bar.style.width = `${Math.round(state.progress * 100)}%`;
      text.textContent = state.text;
      actions.hidden = state.kind === "wait" && performance.now() - t0 < STUCK_MS;
    };
    el.querySelector(".boot-skip").addEventListener("click", () => { skipped = true; close(); });
    el.querySelector(".boot-retry").addEventListener("click", async () => {
      try { await fetch("/api/data/prepare", { method: "POST" }); } catch { /* повторимо опитування нижче */ }
    });

    const loaded = document.readyState === "complete"
      ? Promise.resolve()
      : new Promise((resolve) => window.addEventListener("load", resolve, { once: true }));
    const sky = window.__skyReady ? Promise.resolve()
      : Promise.race([new Promise((resolve) => window.addEventListener("sky-ready", resolve, { once: true })), sleep(SKY_WAIT_MS)]);

    (async () => {
      let polls = 0;
      for (;;) {
        if (skipped) return;
        let state;
        try {
          const res = await fetch("/api/data/status", { cache: "no-store" });
          state = loaderState(await res.json(), polls);
        } catch { state = { kind: "ready", progress: 1, text: "" }; } // стан недоступний — не тримаємо сторінку
        show(state);
        if (state.kind === "ready") break;
        polls += 1;
        await sleep(POLL_MS);
      }
      await Promise.all([loaded, sky]);
      if (!skipped) close();
    })();
  }
}
