// Тести спільного стану (app/static/js/state.js) у Node без браузера.
// Запуск: node --test tests/js/test_state.mjs (або pytest tests/test_state_js.py).
// Кожна «вкладка» — свіжий екземпляр модуля з власними location, history і localStorage.
import { test } from "node:test";
import assert from "node:assert/strict";

const STATE_URL = new URL("../../app/static/js/state.js", import.meta.url);
let instance = 0;

class MemoryStorage {
  constructor(init = {}) { this.data = new Map(Object.entries(init).map(([k, v]) => [k, JSON.stringify(v)])); }
  getItem(key) { return this.data.has(key) ? this.data.get(key) : null; }
  setItem(key, value) { this.data.set(key, String(value)); }
}

async function openTab(href, storage = new MemoryStorage(), { failReplace = false } = {}) {
  const url = new URL(href, "http://localhost:5000");
  const tab = { url, storage, replaceCalls: 0 };
  const define = (name, value) => Object.defineProperty(globalThis, name, { configurable: true, writable: true, value });
  define("location", {
    get pathname() { return url.pathname; },
    get search() { return url.search; },
    get hash() { return url.hash; },
  });
  define("history", {
    state: null,
    replaceState(_data, _title, next) {
      if (failReplace) throw new Error("SecurityError: too many calls");
      const n = new URL(next, url);
      url.pathname = n.pathname;
      url.search = n.search;
      url.hash = n.hash;
      tab.replaceCalls += 1;
    },
  });
  define("localStorage", storage);
  tab.mod = await import(`${STATE_URL.href}?tab=${++instance}`);
  return tab;
}

// Місце й координати — з каталогу app/data/sites.json; решта значень — довільні в межах контракту.
const SHARED = {
  datetime: "2027-07-01T06:30Z",
  site: "Apollo 11 (Море Спокою)",
  lat: 0.67416,
  lon: 23.47314,
  height_m: 2.5,
  mode: "sun-moon-earth",
  compare: ["apollo-11", "apollo-12"],
};

test("посилання відкриває той самий стан в іншій вкладці", async () => {
  const a = await openTab("/system/sun-moon-earth#view");
  a.mod.setState(SHARED);
  assert.deepEqual(a.mod.getState(), SHARED);
  assert.equal(a.url.pathname, "/system/sun-moon-earth", "шлях сторінки не змінюється");
  assert.equal(a.url.hash, "#view", "якір зберігається");
  for (const key of ["datetime", "site", "lat", "lon", "height", "mode", "compare"]) {
    assert.ok(a.url.searchParams.has(key), `у URL є ${key}`);
  }
  const link = a.url.href;

  // Інша вкладка з іншим збереженим станом: посилання має переважити localStorage.
  const other = new MemoryStorage({ "lse-state": { datetime: "2030-01-01T00:00Z", site: "Інше", lat: -89, lon: 0, height_m: 10 } });
  const b = await openTab(link, other);
  assert.deepEqual(b.mod.getState(), SHARED);
  assert.equal(b.url.href, link, "URL другої вкладки не переписується");
});

test("URL оновлюється без перезавантаження при кожній зміні", async () => {
  const tab = await openTab("/moon");
  const before = tab.replaceCalls;
  tab.mod.setState({ lat: -89.5, lon: 0, site: null });
  assert.equal(tab.replaceCalls, before + 1);
  assert.equal(tab.url.searchParams.get("lat"), "-89.5");
  assert.equal(tab.url.searchParams.has("site"), false, "site = null не пишеться");
  tab.mod.setState({ height_m: 0, mode: "earth-moon", compare: [] });
  for (const key of ["height", "mode", "compare"]) {
    assert.equal(tab.url.searchParams.has(key), false, `значення за замовчуванням ${key} не пишеться`);
  }
});

test("без параметрів стан береться з localStorage і одразу потрапляє в URL", async () => {
  const stored = { datetime: "2027-03-15T12:00Z", site: null, lat: -89.9, lon: 0, height_m: 3, mode: "earth-moon", compare: [] };
  const tab = await openTab("/moon", new MemoryStorage({ "lse-state": stored }));
  assert.deepEqual(tab.mod.getState(), stored);
  assert.equal(tab.url.searchParams.get("datetime"), "2027-03-15T12:00Z");
  assert.equal(tab.url.searchParams.get("height"), "3");
});

test("старий збережений стан без нових ключів доповнюється значеннями за замовчуванням", async () => {
  const tab = await openTab("/moon", new MemoryStorage({ "lse-state": { datetime: "2027-03-15T12:00Z", site: null, lat: 1, lon: 2 } }));
  const st = tab.mod.getState();
  assert.equal(st.height_m, 0);
  assert.equal(st.mode, "earth-moon");
  assert.deepEqual(st.compare, []);
});

test("посилання — повний знімок: відсутні ключі не підмішуються з localStorage", async () => {
  const stored = { datetime: "2030-01-01T00:00Z", site: "Інше місце", lat: -89.9, lon: 0, height_m: 10, mode: "sun-moon-earth", compare: ["apollo-11", "apollo-12"] };
  const tab = await openTab("/moon?datetime=2027-07-01T00:00Z", new MemoryStorage({ "lse-state": stored }));
  const st = tab.mod.getState();
  assert.equal(st.datetime, "2027-07-01T00:00Z");
  assert.equal(st.site, null);
  assert.equal(st.lat, null);
  assert.equal(st.height_m, 0);
  assert.equal(st.mode, "earth-moon");
  assert.deepEqual(st.compare, []);
});

test("стан із посилання зберігається, і перехід через меню його не губить (F12)", async () => {
  // Сценарій рев'ю PR #15: у localStorage старий стан, відкрили посилання, перейшли в «Систему».
  const old = { datetime: "2030-01-01T00:00Z", site: "Інше місце", lat: -89.9, lon: 0, height_m: 10, mode: "earth-moon", compare: [] };
  const storage = new MemoryStorage({ "lse-state": old });
  const link = await openTab(`/moon?${new URLSearchParams({ datetime: SHARED.datetime, site: SHARED.site, lat: SHARED.lat, lon: SHARED.lon, height: SHARED.height_m, mode: SHARED.mode, compare: SHARED.compare.join(",") })}`, storage);
  assert.deepEqual(link.mod.getState(), SHARED);
  assert.deepEqual(JSON.parse(storage.getItem("lse-state")), SHARED, "знімок посилання записано в localStorage одразу при завантаженні");

  const menu = await openTab("/system", storage); // посилання меню — без параметрів
  assert.deepEqual(menu.mod.getState(), SHARED);
  assert.equal(menu.url.searchParams.get("datetime"), SHARED.datetime);
});

test("недоступний localStorage не заважає відкрити посилання", async () => {
  const broken = { getItem() { throw new Error("SecurityError"); }, setItem() { throw new Error("SecurityError"); } };
  const tab = await openTab("/moon?datetime=2027-07-01T00:00Z&lat=1&lon=2", broken);
  assert.equal(tab.mod.getState().lat, 1);
});

test("parseUrlState відкидає некоректні значення", async () => {
  const { parseUrlState } = (await openTab("/")).mod;
  assert.deepEqual(parseUrlState("?datetime=вчора&lat=&lon=abc&height=-1&mode=moon&compare=Bad%20Id,!x"), { compare: [] });
  assert.deepEqual(parseUrlState("?lat=95&lon=361&height=1001"), {});
  assert.deepEqual(parseUrlState("?lat=-90&lon=360&height=1000"), { lat: -90, lon: 360, height_m: 1000 });
  // Обидві форми compare: через кому й повторенням параметра (як у GET /compare); дублікати прибираються.
  assert.deepEqual(parseUrlState("?compare=apollo-11,apollo-12&compare=apollo-11&compare=apollo-14").compare, ["apollo-11", "apollo-12", "apollo-14"]);
});

test("datetime з URL нормалізується до UTC «YYYY-MM-DDTHH:mmZ» (F13)", async () => {
  const { normalizeDatetime, parseUrlState } = (await openTab("/")).mod;
  const cases = {
    "2027-07-01T12:00Z": "2027-07-01T12:00Z",
    "2027-07-01t12:00z": "2027-07-01T12:00Z",
    "2027-07-01T12:00:59Z": "2027-07-01T12:00Z", // секунди відкидаються, як у календарі
    "2027-07-01T12:00:00.000Z": "2027-07-01T12:00Z",
    "2027-07-01T12:00:00+02:00": "2027-07-01T10:00Z", // приклад із рев'ю PR #15
    "2027-07-01T12:00:00+0200": "2027-07-01T10:00Z",
    "2027-07-01T12:00:00 02:00": "2027-07-01T10:00Z", // незакодований «+» у URL
    "2027-07-01T00:30-03:30": "2027-07-01T04:00Z",
    "2027-07-01T23:30-01:00": "2027-07-02T00:30Z", // перехід через північ
    "2028-02-29T12:00Z": "2028-02-29T12:00Z", // високосний рік
    "2027-07-01T12:00": "2027-07-01T12:00Z", // без зони — UTC
  };
  for (const [raw, expected] of Object.entries(cases)) assert.equal(normalizeDatetime(raw), expected, raw);
  const rejected = [
    "2027-07-01", // дата без часу — зауваження рев'ю
    "2027-07-01T",
    "2027-07-01T12",
    "2027-02-30T00:00Z", // Date.parse «перекочує» на 2 березня
    "2027-02-29T00:00Z",
    "2027-13-01T00:00Z",
    "2027-07-01T24:00Z",
    "2027-07-01T12:60Z",
    "2027-07-01T12:00+25:00",
    "1814432400000",
    "вчора",
    "",
    null,
  ];
  for (const raw of rejected) assert.equal(normalizeDatetime(raw), undefined, String(raw));

  assert.equal(parseUrlState("?datetime=2027-07-01T12:00:00%2B02:00").datetime, "2027-07-01T10:00Z");
  assert.equal(parseUrlState("?datetime=2027-07-01T12:00:00+02:00").datetime, "2027-07-01T10:00Z");
  assert.equal("datetime" in parseUrlState("?datetime=2027-07-01"), false);
});

test("посилання з датою в іншій зоні відкривається в UTC і адреса виправляється", async () => {
  const tab = await openTab("/moon?datetime=2027-07-01T12:00:00%2B02:00&lat=1&lon=2");
  assert.equal(tab.mod.getState().datetime, "2027-07-01T10:00Z");
  assert.equal(tab.url.searchParams.get("datetime"), "2027-07-01T10:00Z");
});

test("serializeUrlState зберігає чужі параметри й читається назад", async () => {
  const { parseUrlState, serializeUrlState } = (await openTab("/")).mod;
  const query = serializeUrlState(SHARED, "?debug=1&lat=5");
  const params = new URLSearchParams(query);
  assert.equal(params.get("debug"), "1");
  assert.equal(params.getAll("lat").length, 1, "старе значення lat замінено");
  assert.match(query, /datetime=2027-07-01T06:30Z/, "двокрапка не екранується");
  assert.match(query, /compare=apollo-11,apollo-12/, "кома не екранується");
  assert.deepEqual(parseUrlState(`?${query}`), SHARED);
});

test("помилка history.replaceState не ламає setState", async () => {
  const tab = await openTab("/moon", new MemoryStorage(), { failReplace: true });
  const seen = [];
  tab.mod.subscribe((st) => seen.push(st.lat));
  tab.mod.setState({ lat: 12, lon: 34 });
  assert.deepEqual(seen, [null, 12]);
  assert.equal(JSON.parse(tab.storage.getItem("lse-state")).lat, 12);
});

test("getState повертає копію списку порівняння", async () => {
  const tab = await openTab("/?compare=apollo-11,apollo-12");
  tab.mod.getState().compare.push("apollo-14");
  assert.deepEqual(tab.mod.getState().compare, ["apollo-11", "apollo-12"]);
});
