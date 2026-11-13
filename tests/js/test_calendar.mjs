// Тести календаря (app/static/js/calendar.js) у Node без браузера.
// Запуск: node --test tests/js/test_calendar.mjs (або pytest tests/test_state_js.py).
import { test } from "node:test";
import assert from "node:assert/strict";

const CAL_URL = new URL("../../app/static/js/calendar.js", import.meta.url);
const STATE_URL = new URL("../../app/static/js/state.js", import.meta.url);
const { shiftDatetime, STEPS, SYNODIC_MONTH_DAYS } = await import(CAL_URL.href);

test("кроки ±1 год і ±1 доба, зокрема через межу місяця й 29 лютого", () => {
  assert.equal(shiftDatetime("2027-07-01T10:00Z", STEPS.hour), "2027-07-01T11:00Z");
  assert.equal(shiftDatetime("2027-07-01T00:30Z", -STEPS.hour), "2027-06-30T23:30Z");
  assert.equal(shiftDatetime("2027-06-30T23:30Z", STEPS.day), "2027-07-01T23:30Z");
  assert.equal(shiftDatetime("2028-02-28T12:00Z", STEPS.day), "2028-02-29T12:00Z");
  assert.equal(shiftDatetime("2027-02-28T12:00Z", STEPS.day), "2027-03-01T12:00Z");
});

test("крок ±1 лунна доба = 29,530589 доби, округлено до хвилини", () => {
  assert.equal(STEPS.lunar, SYNODIC_MONTH_DAYS * 86_400_000);
  // 0,530589 доби = 12 год 44,048 хв → округлено до 12 год 44 хв.
  assert.equal(shiftDatetime("2027-07-01T10:00Z", STEPS.lunar), "2027-07-30T22:44Z");
  assert.equal(shiftDatetime("2027-07-30T22:44Z", -STEPS.lunar), "2027-07-01T10:00Z");
});

test("крок уперед і назад повертає ту саму хвилину", () => {
  for (let minute = 0; minute < 24 * 60; minute += 7) {
    const start = new Date(Date.UTC(2027, 6, 1, 0, minute)).toISOString().slice(0, 16) + "Z";
    for (const step of Object.values(STEPS)) {
      assert.equal(shiftDatetime(shiftDatetime(start, step), -step), start, `${start} ± ${step}`);
    }
  }
});

test("некоректна дата в стані — крок від поточного часу", () => {
  const now = Date.UTC(2027, 0, 1, 0, 0);
  assert.equal(shiftDatetime("вчора", STEPS.hour, now), "2027-01-01T01:00Z");
  assert.equal(shiftDatetime(undefined, -STEPS.day, now), "2026-12-31T00:00Z");
});

// Мінімальна імітація DOM: поле календаря й кнопки кроку з base.html.
function fakeElement(dataset = {}) {
  const handlers = {};
  return {
    value: "",
    dataset,
    addEventListener(type, fn) { handlers[type] = fn; },
    fire(type) { handlers[type]?.(); },
  };
}

test("кнопки кроку змінюють спільний стан, а поле стежить за станом", async () => {
  const input = fakeElement();
  const buttons = [
    fakeElement({ calStep: "lunar", calDir: "-1" }),
    fakeElement({ calStep: "day", calDir: "-1" }),
    fakeElement({ calStep: "hour", calDir: "-1" }),
    fakeElement({ calStep: "hour", calDir: "1" }),
    fakeElement({ calStep: "day", calDir: "1" }),
    fakeElement({ calStep: "lunar", calDir: "1" }),
  ];
  globalThis.document = {
    getElementById: (id) => (id === "calendar-input" ? input : null),
    querySelectorAll: (sel) => (sel === "[data-cal-step]" ? buttons : []),
  };
  try {
    const { setState, getState } = await import(STATE_URL.href);
    await import(`${CAL_URL.href}?dom=1`);
    setState({ datetime: "2027-07-01T10:00Z" });
    assert.equal(input.value, "2027-07-01T10:00", "поле показує дату стану без Z");

    buttons[3].fire("click"); // +1 год
    assert.equal(getState().datetime, "2027-07-01T11:00Z");
    buttons[4].fire("click"); // +1 доба
    assert.equal(getState().datetime, "2027-07-02T11:00Z");
    buttons[5].fire("click"); // +29,53 доби: 2 лип 11:00 + 29 діб 12 год 44 хв
    assert.equal(getState().datetime, "2027-07-31T23:44Z");
    buttons[0].fire("click"); // −29,53 доби
    buttons[1].fire("click"); // −1 доба
    buttons[2].fire("click"); // −1 год
    assert.equal(getState().datetime, "2027-07-01T10:00Z");
    assert.equal(input.value, "2027-07-01T10:00");

    // Дату змінив інший модуль (напр. кнопка «зараз» у 3D-виді) — поле оновлюється.
    setState({ datetime: "2030-05-05T05:05Z" });
    assert.equal(input.value, "2030-05-05T05:05");

    // Ручне введення в полі.
    input.value = "2031-01-02T03:04";
    input.fire("change");
    assert.equal(getState().datetime, "2031-01-02T03:04Z");
  } finally {
    delete globalThis.document;
  }
});
