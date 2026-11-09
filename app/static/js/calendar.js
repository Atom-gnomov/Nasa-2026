// Модуль «Календар»: спільна дата/час (UTC) для всіх вкладок.
// TODO: вибір діапазону дат, швидкі кроки (±1 год, ±1 доба, ±1 лунна доба).
import { getState, setState } from "./state.js";

const input = document.getElementById("calendar-input");
if (input) {
  input.value = getState().datetime.replace("Z", "").slice(0, 16);
  input.addEventListener("change", () => {
    if (input.value) setState({ datetime: input.value + "Z" });
  });
}
