// Екран завантаження: логотип крутиться, поки сторінка не завантажилась і застосунок не підготував дані NASA (/api/data/status).
// Холодний старт на хостингу (дані ще завантажуються з пакетів) тримає екран до готовності, але не довше MAX_WAIT_MS.
// Логіка очікування — чиста функція (тестується в Node); DOM-частина працює лише в браузері.

const POLL_MS = 1500;
const MAX_WAIT_MS = 60000;

// Відповідь /api/data/status → чи всі набори вже не готуються. Немає відповіді чи наборів — не чекаємо.
export function dataReady(status) {
  return !(status?.datasets ?? []).some((d) => d.state === "running");
}

if (typeof document !== "undefined") {
  const root = document.documentElement;
  const el = document.getElementById("boot-loader");
  if (!el) {
    root.classList.remove("boot-loading");
  } else {
    const t0 = performance.now();
    const sleep = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));
    const loaded = document.readyState === "complete"
      ? Promise.resolve()
      : new Promise((resolve) => window.addEventListener("load", resolve, { once: true }));
    const dataDone = (async () => {
      while (performance.now() - t0 < MAX_WAIT_MS) {
        try {
          const res = await fetch("/api/data/status", { cache: "no-store" });
          if (dataReady(await res.json())) return;
        } catch { return; } // немає зв'язку зі станом — не тримаємо сторінку
        await sleep(POLL_MS);
      }
    })();
    Promise.all([loaded, dataDone]).then(() => {
      root.classList.remove("boot-loading");
      el.classList.add("is-done");
      window.setTimeout(() => el.remove(), 500);
    });
  }
}
