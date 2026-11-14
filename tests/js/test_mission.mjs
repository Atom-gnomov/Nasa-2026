// Тести панелі «Місія» (app/static/js/mission.js) у Node без браузера: запит, формати, підписи.
import { test } from "node:test";
import assert from "node:assert/strict";

const m = await import(new URL("../../app/static/js/mission.js", import.meta.url).href);

const form = (patch = {}) => ({ ...structuredClone(m.DEFAULT_FORM), ...patch });

test("безпілотна: профіль uncrewed, без людей і діб, рівні як id", () => {
  const body = m.buildMissionRequest(form());
  assert.equal(body.mission_profile, "uncrewed");
  assert.equal(body.days, 0);
  assert.equal("crew" in body, false);
  assert.deepEqual(body.sizes, { equipment: "basic", life_support: "basic", comfort: "basic" });
  assert.equal(body.trajectory, "direct");
});

test("пілотована: людей не вказано — їх задає профіль; явне значення переважає", () => {
  assert.equal("crew" in m.buildMissionRequest(form({ crewed: true, crew: null })), false);
  const body = m.buildMissionRequest(form({ crewed: true, crew: 4, days: 30, sizes: { equipment: 3, life_support: 0, comfort: 2 } }));
  assert.equal(body.mission_profile, "crewed");
  assert.equal(body.crew, 4);
  assert.equal(body.days, 30);
  assert.deepEqual(body.sizes, { equipment: "max", life_support: "min", comfort: "extended" });
});

test("ракета й майданчик додаються лише коли вибрані", () => {
  const plain = m.buildMissionRequest(form());
  assert.equal("launch_system_id" in plain || "launch_site_id" in plain, false);
  const body = m.buildMissionRequest(form({ systemId: "ariane-64", siteId: "kourou", trajectory: "low_energy" }));
  assert.equal(body.launch_system_id, "ariane-64");
  assert.equal(body.launch_site_id, "kourou");
  assert.equal(body.trajectory, "low_energy");
});

test("нормалізація форми: сміття → значення за замовчуванням, межі", () => {
  assert.deepEqual(m.normalizeForm(null), m.DEFAULT_FORM);
  assert.deepEqual(m.normalizeForm("рядок"), m.DEFAULT_FORM);
  const f = m.normalizeForm({ crewed: 1, crew: 99, days: -5, sizes: { equipment: 9, comfort: "x" }, trajectory: "teleport", systemId: 5 });
  assert.equal(f.crewed, true);
  assert.equal(f.crew, 6);
  assert.equal(f.days, 0);
  assert.equal(f.sizes.equipment, 3);
  assert.equal(f.sizes.comfort, m.DEFAULT_FORM.sizes.comfort);
  assert.equal(f.trajectory, "direct");
  assert.equal(f.systemId, "");
});

test("формати: маса, діапазон вартості (млн/млрд), ризик, час польоту", () => {
  assert.match(m.fmtKg(1234.4), /1\s?234 кг/);
  assert.equal(m.fmtUsdRange([74_000_000, 269_000_000]), "$74–269 млн");
  assert.equal(m.fmtUsdRange([1_400_000_000, 4_300_000_000]), "$1,4–4,3 млрд");
  assert.equal(m.fmtUsdRange([3_000_000, 8_000_000]), "$3,0–8,0 млн");
  assert.equal(m.fmtRiskRange("помірний", [0.05, 0.21]), "помірний (5,0–21 %)");
  assert.equal(m.fmtDaysRange([3, 5]), "3–5 діб");
  assert.equal(m.fmtDaysRange([4, 4]), "4 діб");
});

test("заповненість ракети: смужка до 100 %, понад 100 % — кілька пусків", () => {
  const ok = m.fillInfo({ utilization: 0.45, launches: 1 });
  assert.equal(ok.percent, 45);
  assert.equal(ok.barPercent, 45);
  assert.equal(ok.over, false);
  const over = m.fillInfo({ utilization: 2.3, launches: 3 });
  assert.equal(over.barPercent, 100);
  assert.equal(over.over, true);
  assert.match(over.text, /3 пуски/);
});

test("тимчасові значення названі прямо: загальна примітка й поля ракети", () => {
  const notes = m.provisionalNotes({
    provisional: true,
    launch_system: { provisional_fields: ["price_usd_per_kg", "failure_probability"], fit: { note: "один пуск не вистачає" } },
  });
  assert.equal(notes.length, 3);
  assert.match(notes[0], /тимчасові/);
  assert.match(notes[1], /ціна за кг, ймовірність відмови/);
  assert.match(notes[2], /^Один пуск не вистачає\.$/);
  assert.equal(m.provisionalNotes({ provisional: false }).length, 0);
});

test("пороги профілю: числові й якісні, вимога чи фільтр", () => {
  assert.equal(m.limitText({ quantity: "landing_slope_deg", comparison: "<", value: 10, unit: "deg", kind: "requirement" }),
    "Нахил майданчика посадки < 10° (вимога)");
  assert.equal(m.limitText({ quantity: "career_effective_dose", comparison: "<", value: 600, unit: "mSv", kind: "requirement" }),
    "Ефективна доза за кар'єру < 600 mSv (вимога)");
  assert.equal(m.limitText({ quantity: "direct_to_earth_comm", comparison: null, value: null, unit: null, kind: "requirement" }),
    "Зв'язок напряму із Землею (вимога)");
  assert.match(m.limitText({ quantity: "sun_visible_fraction", comparison: ">=", value: 5, unit: "%", kind: "screening" }), /фільтр відбору/);
});

test("що задав профіль: людей, пріоритети, пороги — а безпілотна без порогів мовчить про них", () => {
  const crewed = m.profileNote({ profile: { profile: "crewed", from_profile: ["crew", "priorities", "limits.a", "limits.b"] } });
  assert.match(crewed, /кількість людей/);
  assert.match(crewed, /порядок пріоритетів/);
  assert.match(crewed, /2 порогів/);
  assert.match(crewed, /переважають/);
  assert.equal(m.profileNote(null), "");
  assert.equal(m.profileNote({ profile: { profile: "uncrewed", from_profile: [] } }), "");
});

test("склад маси: лише ненульові частини, з назвами", () => {
  const parts = m.partsList({ equipment: 400, life_support: 0, comfort: 0, power_system: 120, structure: 300, margin: 50 });
  assert.equal(parts.length, 4);
  assert.match(parts[0], /^Обладнання: 400 кг$/);
  assert.equal(parts.some((x) => x.startsWith("Життєзабезпечення")), false);
});

test("пуски: українська множина 2–4 «пуски», 5+ і 11–14 «пусків»", () => {
  const word = (n) => (m.fillInfo({ utilization: n - 0.5, launches: n }).text.match(/потрібно \d+ (\S+)/) ?? [])[1];
  assert.equal(word(2), "пуски");
  assert.equal(word(3), "пуски");
  assert.equal(word(5), "пусків");
  assert.equal(word(12), "пусків");
  assert.equal(word(22), "пуски");
  assert.equal(word(54), "пуски");
  assert.equal(word(60), "пусків");
});

test("список засобів запуску: проєктні ракети не видаємо за діючі, діючі першими", () => {
  const list = [
    { id: "lm10", name: "Long March 10", catalog: "rockets", status: "design_target", verified_by_flight: false, active: null, capacity_basis: "tli" },
    { id: "f9", name: "Falcon 9", catalog: "rockets", status: "active", verified_by_flight: true, active: true, capacity_basis: "leo" },
    { id: "vc6", name: "Vulcan VC6", catalog: "rockets", status: "active", verified_by_flight: false, active: true, capacity_basis: "tli" },
    { id: "peg", name: "Pegasus XL", catalog: "launch_systems", active: false, capacity_basis: "leo" },
    { id: "zen", name: "Zenit", catalog: "launch_systems", active: false, capacity_basis: null },
  ];
  const picked = m.selectableVehicles(list);
  assert.deepEqual(picked.map((v) => v.id), ["f9", "vc6", "lm10", "peg"]); // без місткості — не пропонуємо; діючі й підтверджені першими
  assert.equal(m.vehicleLabel(list[1]), "Falcon 9");
  assert.equal(m.vehicleLabel(list[0]), "Long March 10 (проєктна ціль)");
  assert.equal(m.vehicleLabel(list[2]), "Vulcan VC6 (не підтверджено польотом)");
  assert.equal(m.vehicleLabel(list[3]), "Pegasus XL (не діє)");
});

test("місткість на TLI, переведена на НОО, названа в примітках", () => {
  const notes = m.provisionalNotes({ provisional: false, launch_system: { provisional_fields: [], rocket: { capacity_basis: "tli" }, fit: { note: null } } });
  assert.equal(notes.length, 1);
  assert.match(notes[0], /траєкторію до Місяця/);
  assert.equal(m.provisionalNotes({ provisional: false, launch_system: { provisional_fields: [], rocket: { capacity_basis: "leo" }, fit: {} } }).length, 0);
});
