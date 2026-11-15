// Єдина кнопка «Місії» в смузі вкладок: розгортає все планування — десять кроків (вони ведуть на Підбір, Місію, План,
// Вікно запуску, перевірку й звіт), «Мій план», «Мої плани». Окремі вкладки планування сховано під неї, нічого не видалено:
// усі сторінки досяжні через кроки. Стан — у sessionStorage.
// Початковий стан рахує і вбудований скрипт у base.html (до малювання, щоб не блимало) — за тим самим правилом.
export const WIZARD_KEY = "lse-wizard";
export const WIZARD_PAGES = ["/mission", "/plan", "/search", "/launch-window", "/consistency", "/report"];

// Збережений вибір має перевагу; інакше смуга відкрита, коли прийшли з кроку (?step=n) і на сторінках планування
// (Місія, План, Підбір, Вікно запуску, перевірка, звіт); на «Місяці» й «Системі» — згорнута.
export function wizardInitial(stored, pathname = "", search = "") {
  if (stored === "1") return true;
  if (stored === "0") return false;
  return /[?&]step=\d/.test(search) || WIZARD_PAGES.includes(pathname);
}

function init() {
  const btn = document.getElementById("mp-toggle");
  if (!btn) return;
  const root = document.documentElement;
  const apply = (open) => {
    root.dataset.wizard = open ? "open" : "closed";
    btn.setAttribute("aria-expanded", String(open));
    btn.classList.toggle("active", open);
  };
  let stored = null;
  try { stored = sessionStorage.getItem(WIZARD_KEY); } catch { /* приватний режим */ }
  apply(wizardInitial(stored, location.pathname, location.search));
  btn.addEventListener("click", () => {
    const open = root.dataset.wizard !== "open";
    apply(open);
    try { sessionStorage.setItem(WIZARD_KEY, open ? "1" : "0"); } catch { /* не критично */ }
  });
}

if (typeof document !== "undefined") init();
