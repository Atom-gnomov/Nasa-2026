// Банер «Готую дані» (I7, П-11): показує, що застосунок сам готує дані NASA у фоні, і дає повторити після помилки.
// Логіка тексту — чиста функція (тестується в Node); DOM-частина працює лише в браузері.

const POLL_MS = 5000;

// Відповідь /api/data/status → { kind: "hidden" | "running" | "failed", text } для банера.
export function bannerState(status) {
  const sets = status?.datasets ?? [];
  const running = sets.filter((d) => d.state === "running");
  const failed = sets.filter((d) => d.state === "failed");
  if (running.length) {
    const names = running.map((d) => d.label).join("; ");
    const last = running.find((d) => d.message)?.message;
    return { kind: "running", text: `Готую дані: ${names}${last ? ` — ${last}` : ""}. Сайт працює з тим, що вже є.` };
  }
  if (failed.length) {
    const first = failed[0];
    return { kind: "failed", text: `Не вдалося підготувати «${first.label}»: ${first.message ?? "помилка"}.` };
  }
  return { kind: "hidden", text: "" };
}

if (typeof document !== "undefined") {
  const banner = document.getElementById("data-banner");
  if (banner) {
    const text = banner.querySelector(".data-banner-text");
    const retry = banner.querySelector("button");
    let timer = null;
    const refresh = async () => {
      try {
        const res = await fetch("/api/data/status");
        const state = bannerState(await res.json());
        banner.hidden = state.kind === "hidden";
        text.textContent = state.text;
        retry.hidden = state.kind !== "failed";
        clearTimeout(timer);
        if (state.kind === "running") timer = setTimeout(refresh, POLL_MS);
      } catch { banner.hidden = true; }
    };
    retry.addEventListener("click", async () => {
      retry.disabled = true;
      try { await fetch("/api/data/prepare", { method: "POST" }); } finally { retry.disabled = false; }
      refresh();
    });
    refresh();
  }
}
