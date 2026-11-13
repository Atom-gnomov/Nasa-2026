// Модуль «Календар»: спільна дата/час (UTC) для всіх вкладок і кроки ±1 год / ±1 доба / ±1 лунна доба.
// Поле показує дату зі спільного стану й оновлюється, коли її змінює інший модуль (3D-вид системи).
// TODO (друга черга): вибір діапазону дат, відтворення анімації.
import { getState, setState, subscribe } from "./state.js";

// Синодичний місяць — лунна доба, від сходу до сходу Сонця. Те саме значення, що
// SYNODIC_MONTH_DAYS в app/core/constants.py (docs/MATH.md: 29,5306 доби); збіг перевіряє тест.
export const SYNODIC_MONTH_DAYS = 29.530589;
const MINUTE_MS = 60_000;
export const STEPS = {
  hour: 3_600_000,
  day: 86_400_000,
  lunar: SYNODIC_MONTH_DAYS * 86_400_000,
};

// Зсуває дату стану на stepMs. Результат — «YYYY-MM-DDTHH:mmZ», округлений до хвилини,
// тож крок уперед і назад повертає ту саму хвилину. Некоректна дата → відлік від `now`.
export function shiftDatetime(datetime, stepMs, now = Date.now()) {
  const base = Date.parse(datetime);
  const from = Number.isFinite(base) ? base : now;
  const ms = Math.round((from + stepMs) / MINUTE_MS) * MINUTE_MS;
  return new Date(ms).toISOString().slice(0, 16) + "Z";
}

const input = typeof document === "undefined" ? null : document.getElementById("calendar-input");
if (input) {
  subscribe(({ datetime }) => {
    const value = String(datetime).replace("Z", "").slice(0, 16);
    if (input.value !== value) input.value = value;
  });
  input.addEventListener("change", () => {
    if (input.value) setState({ datetime: input.value + "Z" });
  });
  for (const button of document.querySelectorAll("[data-cal-step]")) {
    button.addEventListener("click", () => {
      const step = STEPS[button.dataset.calStep] * Number(button.dataset.calDir);
      if (Number.isFinite(step)) setState({ datetime: shiftDatetime(getState().datetime, step) });
    });
  }
}
