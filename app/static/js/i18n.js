// Модуль «Мова інтерфейсу» (F8): українська (вихідна) і англійська.
//
// Вихідний текст усього інтерфейсу — українська, тому словник (i18n/en.json) відображає український текст
// в англійський, а не ключі: шаблони й модулі лишаються без змін, нові тексти не ламаються (без перекладу
// показується українська). Переклад ставить сам модуль:
//   • текстові вузли й атрибути title / aria-label / placeholder / alt — на старті й при перемиканні;
//   • вузли, які модулі вставляють або змінюють пізніше (MutationObserver) — одразу після вставки;
//   • текст на canvas і складені в коді рядки — через t().
// Порядок підстановки: точний збіг тексту (strings) → підрядки цілими словами, довші першими (phrases).
// Мова — властивість користувача: ?lang=en в адресі (посилання), далі localStorage; за замовчуванням українська.
const KEY = "lse-lang";
export const LANGS = ["uk", "en"];
export const DEFAULT_LANG = "uk";
const CYRILLIC = /[А-Яа-яІіЇїЄєҐґ]/;
const LETTERS = "А-Яа-яІіЇїЄєҐґ'ʼ’";
const ATTRS = ["title", "aria-label", "placeholder", "alt"];
const SKIP = new Set(["SCRIPT", "STYLE", "TEXTAREA", "CODE", "PRE"]);

export const normalize = (text) => text.replace(/\s+/g, " ").trim();

// Мова: ?lang= → збережена → українська.
export function pickLang({ search = "", stored = null } = {}) {
  const fromUrl = new URLSearchParams(search).get("lang");
  if (LANGS.includes(fromUrl)) return fromUrl;
  return LANGS.includes(stored) ? stored : DEFAULT_LANG;
}

const escapeRegExp = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// Словник → функція перекладу рядка. Пробіли на краях зберігаються; без кирилиці рядок не чіпаємо.
export function buildTranslator(dictionary) {
  const strings = new Map(Object.entries(dictionary?.strings ?? {}));
  const phrases = dictionary?.phrases ?? {};
  const keys = Object.keys(phrases).sort((a, b) => b.length - a.length);
  const isLetter = (ch) => new RegExp(`[${LETTERS}]`).test(ch);
  // цілими словами: перед і після підрядка не має стояти літера (одиниця «м» не псує «метр»)
  const pattern = keys.map((k) => `${isLetter(k[0]) ? `(?<![${LETTERS}])` : ""}${escapeRegExp(k)}${isLetter(k.at(-1)) ? `(?![${LETTERS}])` : ""}`);
  const phraseRe = pattern.length ? new RegExp(pattern.join("|"), "g") : null;
  return function translate(text) {
    if (typeof text !== "string" || !CYRILLIC.test(text)) return text;
    const exact = strings.get(normalize(text));
    if (exact !== undefined) return text.match(/^\s*/)[0] + exact + text.match(/\s*$/)[0];
    return phraseRe ? text.replace(phraseRe, (m) => phrases[m]) : text;
  };
}

// {name} у тексті підставляється зі vars: t("Знайдено {n} місць", { n: 5 }).
export function interpolate(text, vars) {
  return vars ? text.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m)) : text;
}

// ---------- Стан модуля ----------
let lang = DEFAULT_LANG;
let translate = (s) => s;
let dictionaryPromise = null;
const listeners = new Set();

export const getLang = () => lang;

// Переклад рядка для коду (canvas, складені рядки). Українською повертає текст як є.
export function t(text, vars) {
  return interpolate(lang === "en" ? translate(text) : text, vars);
}

export function onLangChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

// ---------- DOM ----------
const textRecords = typeof WeakMap === "undefined" ? null : new WeakMap(); // Text → { uk, shown }
const attrRecords = typeof WeakMap === "undefined" ? null : new WeakMap(); // Element → Map(attr → { uk, shown })

function applyText(node) {
  const rec = textRecords.get(node);
  const uk = rec && node.data === rec.shown ? rec.uk : node.data; // текст змінив код сторінки — це новий оригінал
  const shown = lang === "en" ? translate(uk) : uk;
  textRecords.set(node, { uk, shown });
  if (node.data !== shown) node.data = shown;
}

function applyAttr(el, name) {
  const value = el.getAttribute(name);
  if (value === null) return;
  let map = attrRecords.get(el);
  if (!map) attrRecords.set(el, (map = new Map()));
  const rec = map.get(name);
  const uk = rec && value === rec.shown ? rec.uk : value;
  const shown = lang === "en" ? translate(uk) : uk;
  map.set(name, { uk, shown });
  if (value !== shown) el.setAttribute(name, shown);
}

export function translateTree(root) {
  if (!root) return;
  if (root.nodeType === 3) { if (!SKIP.has(root.parentNode?.nodeName)) applyText(root); return; }
  if (root.nodeType !== 1 || SKIP.has(root.nodeName)) return;
  for (const name of ATTRS) if (root.hasAttribute(name)) applyAttr(root, name);
  for (const child of root.childNodes) translateTree(child);
}

let observer = null;
function observe() {
  if (observer || typeof MutationObserver === "undefined") return;
  observer = new MutationObserver((mutations) => {
    for (const m of mutations) {
      if (m.type === "childList") for (const node of m.addedNodes) translateTree(node);
      else if (m.type === "characterData") { if (!SKIP.has(m.target.parentNode?.nodeName)) applyText(m.target); }
      else if (m.type === "attributes") applyAttr(m.target, m.attributeName);
    }
  });
  observer.observe(document.documentElement, {
    childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS,
  });
}

// ---------- Словник і перемикання ----------
function loadDictionary() {
  dictionaryPromise ??= fetch(new URL("./i18n/en.json", import.meta.url))
    .then((res) => { if (!res.ok) throw new Error(res.statusText); return res.json(); })
    .then((dictionary) => { translate = buildTranslator(dictionary); })
    .catch(() => { dictionaryPromise = null; }); // без словника інтерфейс лишається українським
  return dictionaryPromise;
}

function syncUi() {
  document.documentElement.lang = lang;
  for (const b of document.querySelectorAll("[data-lang]")) {
    const active = b.dataset.lang === lang;
    b.classList.toggle("active", active);
    b.setAttribute("aria-pressed", String(active));
  }
}

function syncUrl() {
  try {
    const url = new URL(location.href);
    if (lang === DEFAULT_LANG) url.searchParams.delete("lang"); else url.searchParams.set("lang", lang);
    url.search = url.searchParams.toString().replace(/%3A/gi, ":").replace(/%2C/gi, ","); // як у state.js: читабельні дата й списки
    history.replaceState(history.state, "", url);
  } catch { /* обмеження replaceState не ламають перемикання */ }
}

export async function setLang(next, { persist = true } = {}) {
  if (!LANGS.includes(next)) return false;
  if (next === "en") await loadDictionary();
  lang = next === "en" && translate === undefined ? DEFAULT_LANG : next;
  if (persist) {
    try { localStorage.setItem(KEY, lang); } catch { /* приватний режим */ }
    syncUrl();
  }
  if (lang === "en") observe(); else if (observer) { observer.disconnect(); observer = null; }
  translateTree(document.documentElement);
  syncUi();
  for (const fn of listeners) fn(lang);
  return true;
}

export const ready = (async () => {
  if (typeof document === "undefined") return;
  let stored = null;
  try { stored = localStorage.getItem(KEY); } catch { /* приватний режим */ }
  const initial = pickLang({ search: location.search, stored });
  const start = async () => {
    for (const b of document.querySelectorAll("[data-lang]")) b.addEventListener("click", () => setLang(b.dataset.lang));
    await setLang(initial, { persist: false });
  };
  if (document.readyState === "loading") await new Promise((r) => document.addEventListener("DOMContentLoaded", r, { once: true }));
  await start();
})();
