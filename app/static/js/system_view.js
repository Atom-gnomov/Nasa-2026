// Модуль «3D-вид системи»: режими earth-moon і sun-moon-earth.
// Режими синхронізовані через state.js (спільні дата й місце).
// TODO: Three.js-сцена, положення тіл з API ефемерид, візуалізація радіогоризонту.
import { subscribe } from "./state.js";

const host = document.getElementById("system-view");
if (host) {
  subscribe(({ datetime }) => {
    host.dataset.datetime = datetime;
  });
}
