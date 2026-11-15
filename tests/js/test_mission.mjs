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

// ---------- F19: числа категорій, екіпаж, запаси, журнал ----------
const cs = {
  per_day: { oxygen_kg: 1.8, water_kg: 6.1, food_kg: 4.7 }, loaded_kg: { oxygen: 41.4, water: 140.3, food: 108.1 },
  required_kg: { oxygen: 36, water: 122, food: 94 }, recommended_supply_days: 23, supply_days: 23,
  reserve_fraction_recommended: 0.15, reserve_fraction_planned: 0.15,
  warnings: [{ kind: "low_reserve", message: "мало" }],
  log: [0, 1, 2].map((d) => ({ day: d, remaining_pct: { oxygen: 100 - d * 40, water: 100 - d * 40, food: 100 - d * 40 },
    status: { oxygen: d === 2 ? "shortage" : "ok", water: "ok", food: "reserve" }, worst: d === 2 ? "shortage" : "ok" })),
};

test("повзунок має числа: рівень, маса, вартість, потужність", () => {
  const text = m.categoryNumbers({ mass_kg: 765.4, usd: [76e6, 306e6], power_w: 420 }, "Базовий");
  assert.match(text, /^Базовий: 765 кг · \$76–306 млн · 420 Вт$/);
  assert.equal(m.categoryNumbers(null, "x"), "");
  assert.doesNotMatch(m.categoryNumbers({ mass_kg: 5, usd: [1e5, 2e5], power_w: 0 }, "Мін"), /Вт/);
});

test("запит із біометрією: crew_members замість crew, запаси й резерв лише коли змінені", () => {
  const member = m.defaultMember("female");
  const body = m.buildMissionRequest(form({ crewed: true, crew: 2, days: 10, useBio: true, members: [m.defaultMember("male"), member],
                                            supplyDays: 12, reservePct: 20 }));
  assert.equal(body.crew_members.length, 2);
  assert.ok(!("crew" in body));
  assert.equal(body.supply_days, 12);
  assert.equal(body.reserve_fraction, 0.2);
  const plain = m.buildMissionRequest(form({ crewed: true, crew: 2, useBio: true, members: [m.defaultMember("male")] }));
  assert.ok(!("supply_days" in plain) && !("reserve_fraction" in plain));
  assert.ok(!("crew_members" in m.buildMissionRequest(form({ crewed: false, useBio: true, members: [member] }))));
  assert.ok(!("crew_members" in m.buildMissionRequest(form({ crewed: true, useBio: false, members: [member] }))));
});

test("нормалізація члена екіпажу: еталон статі, межі, не більше шести", () => {
  assert.deepEqual(m.normalizeMember({ sex: "female" }), { sex: "female", activity: "active", age: 35, mass_kg: 62, height_m: 1.65 });
  const n = m.normalizeMember({ sex: "male", mass_kg: 5, height_m: 9, age: "x", activity: "?" });
  assert.equal(n.mass_kg, 35); assert.equal(n.height_m, 2.15); assert.equal(n.age, 35); assert.equal(n.activity, "active");
  const f = m.normalizeForm({ crewed: true, useBio: true, members: Array(9).fill({ sex: "male" }), supplyDays: "12", reservePct: 999 });
  assert.equal(f.members.length, 6); assert.equal(f.supplyDays, 12); assert.equal(f.reservePct, 200);
});

test("роль члена екіпажу (M27): відома зберігається, невідома відкидається, іде в запит", () => {
  assert.equal(m.normalizeMember({ sex: "male", role: "pilot" }).role, "pilot");
  assert.ok(!("role" in m.normalizeMember({ sex: "male", role: "janitor" })));
  const body = m.buildMissionRequest(form({ crewed: true, useBio: true, members: [{ sex: "male", role: "scientist" }] }));
  assert.equal(body.crew_members[0].role, "scientist");
});

test("запаси й журнал: рядки без undefined, відсотки й стани, попередження", () => {
  const rows = m.suppliesRows(cs);
  assert.equal(rows.length, 3);
  for (const r of rows) for (const c of r) assert.ok(!/undefined|NaN/.test(c), c);
  assert.match(m.reserveText(cs), /Рекомендовано 23 діб \(резерв 15 %\), заплановано 23 діб \(резерв 15 %\)/);
  const log = m.logRows(cs);
  assert.equal(log.length, 3);
  assert.deepEqual(log[2].cells, ["2", "20 %", "20 %", "20 %"]);
  assert.equal(log[2].worst, "shortage");
  assert.deepEqual(log[2].status, ["shortage", "ok", "reserve"]);
  assert.deepEqual(m.warningTexts(cs), ["мало"]);
  assert.deepEqual(m.warningTexts(null), []);
});

test("журнал довгої місії проріджується, але перший і останній рядки лишаються", () => {
  const long = { log: Array.from({ length: 366 }, (_, d) => ({ day: d, remaining_pct: { oxygen: 1, water: 1, food: 1 },
                                                              status: { oxygen: "ok", water: "ok", food: "ok" }, worst: "ok" })) };
  const rows = m.logRows(long, 40);
  assert.ok(rows.length <= 41 && rows[0].cells[0] === "0" && rows.at(-1).cells[0] === "365");
});

test("довільні обсяги запасів: запит supply_kg лише для заданих; нормалізація; повзунок і підсумок", () => {
  const body = m.buildMissionRequest(form({ crewed: true, crew: 1, useBio: true, members: [m.defaultMember("male")],
                                            supplyKg: { oxygen: 5, water: null, food: 40 } }));
  assert.deepEqual(body.supply_kg, { oxygen: 5, food: 40 });
  const none = m.buildMissionRequest(form({ crewed: true, crew: 1, useBio: true, members: [m.defaultMember("male")] }));
  assert.ok(!("supply_kg" in none));
  const f = m.normalizeForm({ supplyKg: { oxygen: "7", water: -3, food: 1e9, extra: 1 } });
  assert.deepEqual(f.supplyKg, { oxygen: 7, water: 0, food: 100000 });
  const res = { crew_supplies: { days: 10, loaded_total_kg: 100, per_day: {}, loaded_kg: {}, required_kg: {},
    resources: { oxygen: { loaded_kg: 4, recommended_kg: 10, runs_out_day: 4, excess_kg: 0, covers_days: 4, balance_kg: -6, required_kg: 10 },
                 water: { loaded_kg: 60, recommended_kg: 20, runs_out_day: null, excess_kg: 40, covers_days: 30, balance_kg: 40, required_kg: 18 } },
    summary: { mission_ok: false, first_shortage_day: 4, first_shortage_resource: "oxygen", excess_kg: 40, deficit_kg: 6, critical: true },
    economics: { loaded_usd: [1e5, 3e5], excess_usd: [4e4, 1.2e5], deficit_usd: [6e3, 1.8e4] } } };
  const lines = m.summaryLines(res);
  assert.equal(lines[0].kind, "crit");
  assert.match(lines[0].text, /кисень закінчується на добі 4 з 10/);
  assert.ok(lines.some((l) => l.kind === "crit" && /Нестача/.test(l.text) && /\$6,0–18 тис\./.test(l.text)));
  assert.ok(lines.some((l) => l.kind === "warn" && /Надлишок/.test(l.text) && /\$40–120 тис\./.test(l.text)));
  const s = m.supplySlider(res.crew_supplies, "oxygen", null);
  assert.equal(s.status, "shortage"); assert.equal(s.auto, true); assert.equal(s.rec, 10); assert.ok(s.max >= 20);
  assert.equal(m.supplySlider(res.crew_supplies, "water", 60).status, "excess");
  assert.equal(m.supplySlider(null, "oxygen", null), null);
  assert.equal(m.fmtUsdAny([500, 900]), "$500–900");
});

test("своя маса категорії й позиції каталогу: запит, нормалізація, виноски", () => {
  const body = m.buildMissionRequest(form({ crewed: true, crew: 1, categoryKg: { equipment: 500, life_support: null, comfort: 80 },
                                            equipmentItems: { viper_rover: 2, trident_drill: 0 } }));
  assert.deepEqual(body.category_kg, { equipment: 500, comfort: 80 });
  assert.deepEqual(body.equipment_items, [{ id: "viper_rover", count: 2 }]);
  const uncrewed = m.buildMissionRequest(form({ crewed: false, categoryKg: { equipment: 5, comfort: 80 } }));
  assert.deepEqual(uncrewed.category_kg, { equipment: 5 }, "без екіпажу — лише обладнання");
  const plain = m.buildMissionRequest(form({ crewed: true, crew: 1 }));
  assert.ok(!("category_kg" in plain) && !("equipment_items" in plain));
  const f = m.normalizeForm({ categoryKg: { equipment: "12", comfort: -4, life_support: 1e9, x: 1 },
                              equipmentItems: { viper_rover: "3", "Bad Id": 2, zero: 0, many: 999 } });
  assert.deepEqual(f.categoryKg, { equipment: 12, life_support: 100000, comfort: 0 });
  assert.deepEqual(f.equipmentItems, { viper_rover: 3, many: 50 });
  const breakdown = { life_support: [{ key: "consumables", kg: 100 }, { key: "shield", kg: 0 }, { key: "fixed", kg: 300 }] };
  const rows = m.breakdownRows(breakdown, "life_support");
  assert.equal(rows.length, 2); assert.match(rows[0][0], /Витратні матеріали \(consumables\)/); assert.equal(rows[0][1], "100 кг");
  assert.deepEqual(m.breakdownRows(null, "comfort"), []);
  const item = { mass_kg: [10, 15], power_w: [30, 195], supply_power_w: 40000 };
  const info = m.itemInfo(item, [1e6, 1.2e6]);
  assert.match(info, /маса 10–15 кг/); assert.match(info, /доставка ≈ \$10–18 млн/); assert.match(info, /30–195 Вт/); assert.match(info, /дає 40 кВт/);
  assert.match(m.equipmentSummary({ mass_range_kg: [6950, 6950], delivery_usd: [6.95e9, 8.34e9] }), /6\s950 кг.*\$7,0–8,3 млрд/);
  assert.equal(m.equipmentSummary(null), "");
});

test("крок 7: підсумок позицій із потужністю, рекомендації за метою, попередження", () => {
  const eq = { mass_range_kg: [475, 475], delivery_usd: [4.75e8, 5.7e8], power_w: 0, supply_power_w: 0 };
  assert.doesNotMatch(m.equipmentSummary(eq), /Споживання|Дають/);
  const withPower = m.equipmentSummary({ ...eq, power_w: 195, supply_power_w: 40000 });
  assert.match(withPower, /Споживання до 195 Вт/);
  assert.match(withPower, /Дають 40 кВт/);
  const catalog = { items: [{ id: "viper_rover", stage: "mobility" }, { id: "trident_drill", stage: "isru" }, { id: "fsp_reactor", stage: "power" }, { id: "clps_instrument", stage: "science" }] };
  assert.deepEqual(m.recommendedItems("ice", catalog).map((x) => x.id), ["viper_rover", "trident_drill", "clps_instrument"]);
  assert.deepEqual(m.recommendedItems("base", catalog).map((x) => x.id), ["viper_rover", "trident_drill", "fsp_reactor"]);
  assert.deepEqual(m.recommendedItems("", catalog), []);
  assert.deepEqual(m.recommendedItems("ice", null), []);
  const r = { cost: { launches: 1, utilization: 0.5 }, equipment: { power_w: 100, supply_power_w: 0 } };
  assert.deepEqual(m.payloadWarnings(r), []);
  assert.deepEqual(m.payloadWarnings(null), []);
  const multi = m.payloadWarnings({ ...r, cost: { launches: 2, utilization: 1.3 } });
  assert.equal(multi.length, 1);
  assert.match(multi[0], /не вміщується в одну ракету/);
  const over = m.payloadWarnings({ ...r, equipment: { power_w: 50000, supply_power_w: 40000 } });
  assert.match(over[0], /перевищує потужність реактора/);
});
