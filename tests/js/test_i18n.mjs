// Тести перекладача інтерфейсу (app/static/js/i18n.js) у Node без браузера: вибір мови, пошук у словнику,
// підрядки цілими словами, підстановка, а також регресійні приклади на справжньому словнику en.json.
// Запуск: node --test tests/js/test_i18n.mjs (або pytest tests/test_state_js.py).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const i18n = await import(new URL("../../app/static/js/i18n.js", import.meta.url).href);
const real = JSON.parse(readFileSync(new URL("../../app/static/js/i18n/en.json", import.meta.url), "utf8"));
const tr = i18n.buildTranslator(real);

test("мова: ?lang= → збережена → українська за замовчуванням; чужі значення відкидаються", () => {
  assert.equal(i18n.pickLang({}), "uk");
  assert.equal(i18n.pickLang({ search: "?lang=en" }), "en");
  assert.equal(i18n.pickLang({ search: "?datetime=2027-07-01T00:00Z&lang=en&lat=1" }), "en");
  assert.equal(i18n.pickLang({ stored: "en" }), "en");
  assert.equal(i18n.pickLang({ search: "?lang=uk", stored: "en" }), "uk", "посилання важливіше за збережене");
  assert.equal(i18n.pickLang({ search: "?lang=de", stored: "fr" }), "uk");
  assert.equal(i18n.pickLang({ search: "?lang=" }), "uk");
});

test("точний збіг: пробіли на краях зберігаються, внутрішні згортаються, без кирилиці — не чіпаємо", () => {
  const t = i18n.buildTranslator({ strings: { "Дата (UTC)": "Date (UTC)", "а б": "a b" } });
  assert.equal(t("Дата (UTC)"), "Date (UTC)");
  assert.equal(t("  Дата (UTC)\n"), "  Date (UTC)\n");
  assert.equal(t("а\n   б"), "a b");
  assert.equal(t("Date (UTC)"), "Date (UTC)");
  assert.equal(t("DSN"), "DSN");
  assert.equal(t(""), "");
  assert.equal(t(null), null);
});

test("підрядки: цілими словами, довші першими, межі з не-літерою (крапка, дужка) працюють", () => {
  const t = i18n.buildTranslator({ phrases: { "до заходу": "until set", "до": "to", "км": "km", "м": "m", "пн.": "N", "год": "h" } });
  assert.equal(t("до заходу 3 год"), "until set 3 h", "довша фраза перемагає «до»");
  assert.equal(t("5 км і 10 м"), "5 km і 10 m");
  assert.equal(t("метр"), "метр", "«м» не псує слово «метр»");
  assert.equal(t("годину"), "годину", "«год» не псує слово «годину»");
  assert.equal(t("(пн.)"), "(N)");
  assert.equal(t("пн.-сх."), "N-сх.");
});

test("підстановка {name}: ні дужки без змінної, ні зайві змінні не ламають текст", () => {
  assert.equal(i18n.interpolate("Знайдено {n} місць", { n: 5 }), "Знайдено 5 місць");
  assert.equal(i18n.interpolate("{a} і {b}", { a: 1 }), "1 і {b}");
  assert.equal(i18n.interpolate("без змінних", { n: 5 }), "без змінних");
  assert.equal(i18n.interpolate("{n}", undefined), "{n}");
  assert.equal(i18n.t("Земля (освітлено {p} %)", { p: 36 }), "Земля (освітлено 36 %)", "українською текст не змінюється");
});

test("словник en.json: вигляд і цілісність", () => {
  assert.ok(Object.keys(real.strings).length > 250 && Object.keys(real.phrases).length > 60);
  const cyr = /[А-Яа-яІіЇїЄєҐґ]/;
  for (const [uk, en] of Object.entries(real.strings)) {
    assert.ok(cyr.test(uk), `ключ без кирилиці: ${uk}`);
    assert.ok(en.trim() && !cyr.test(en), `переклад порожній або з кирилицею: ${uk} → ${en}`);
    const holes = (s) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(",");
    assert.equal(holes(uk), holes(en), `різні змінні {…}: ${uk}`);
  }
  for (const [uk, en] of Object.entries(real.phrases)) assert.ok(en.trim() && !cyr.test(en), `${uk} → ${en}`);
});

test("регресія на справжньому словнику: статичні рядки інтерфейсу", () => {
  assert.equal(tr("Місяць"), "Moon");
  assert.equal(tr("Дата (UTC)"), "Date (UTC)");
  assert.equal(tr("Сонце й енергія"), "Sun and energy");
  assert.equal(tr("Рельєф: низини / височини"), "Relief: lowlands / highlands");
  assert.equal(tr("Виберіть місце на Місяці"), "Select a site on the Moon");
  assert.equal(tr("Режим якості 3D; зберігається на цьому пристрої"), "3D quality mode, saved on this device");
});

test("регресія: складені рядки з числами — одиниці, події Сонця й Землі, сторони світу", () => {
  assert.equal(tr("114 год (4.7 доби)"), "114 h (4.7 days)");
  assert.equal(tr("немає за 30 діб"), "none within 30 days");
  assert.equal(tr("так (36 % диска)"), "yes (36 % of the disc)");
  assert.equal(tr("1.222 с в один бік"), "1.222 s one-way");
  assert.equal(tr("307 Вт"), "307 W");
  assert.equal(tr("1312 Вт/м²"), "1312 W/m²");
  assert.equal(tr("12.1 кВт·год"), "12.1 kWh");
  assert.equal(tr("1 251 мкЗв/добу (≈ 457 мЗв/рік)"), "1 251 µSv/day (≈ 457 mSv/yr)");
  assert.equal(tr("0.6742° пн., 23.4731° сх."), "0.6742° N, 23.4731° E");
  assert.equal(tr("26.1324° пн., 3.6333° зх."), "26.1324° N, 3.6333° W");
  assert.equal(tr("-1 924 м (LOLA LDEM_64, 474 м/пікс.)"), "-1 924 m (LOLA LDEM_64, 474 m/px)");
  assert.equal(
    tr("Сонце: 12.07°, над горизонтом, до заходу Сонця — немає до кінця періоду"),
    "Sun: 12.07°, above the horizon, until sunset — none until the end of the period",
  );
  assert.equal(tr("Земля: 69.84°, освітлено 36 %, під горизонтом"), "Earth: 69.84°, lit 36 %, below the horizon");
  assert.equal(tr("DSN: немає зв'язку"), "DSN: no contact");
  assert.equal(tr("a = 0.999995 а.о., e = 0.01671, період 365.25 д"), "a = 0.999995 AU, e = 0.01671, period 365.25 d");
  assert.equal(tr("спадаючий місяць, освітлено 95.2%"), "waning Moon, lit 95.2%");
});

test("регресія: назви місць із каталогу й атрибути списку пріоритетів", () => {
  assert.equal(tr("Apollo 11 (Море Спокою)"), "Apollo 11 (Sea of Tranquility)");
  assert.equal(tr("Apollo 15 (Гедлі–Апенніни)"), "Apollo 15 (Hadley–Apennine)");
  assert.equal(tr("Goldstone (США)"), "Goldstone (USA)");
  assert.equal(tr("Кратер Шеклтон (центр)"), "Shackleton crater (center)");
  assert.equal(tr("Враховувати: Енергія"), "Include: Energy");
  assert.equal(tr("Зв'язок: менш важливо"), "Communications: less important");
});

test("шаблони речень із виглядом з поверхні дають повне англійське речення без кирилиці", () => {
  const vars = { src: "LOLA X", pat: "surface", d: 200, max: "9.6", sky: 91, eye: 2, pole: "", from: "01.07", sun: 3, comm: 43, terrain: "smooth sphere" };
  for (const key of Object.keys(real.strings).filter((k) => k.includes("{"))) {
    const out = i18n.interpolate(tr(key), vars);
    assert.ok(!/[А-Яа-яІіЇїЄє]/.test(out), `${key} → ${out}`);
  }
});
