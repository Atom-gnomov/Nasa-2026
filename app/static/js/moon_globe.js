// Модуль «Глобус Місяця» (вкладка «Місяць»).
// Список місць і введення координат; сам 3D-глобус — globe_view.js.
import { getState, setState, subscribe } from "./state.js";

const select = document.getElementById("site-select");
const latInput = document.getElementById("lat-input");
const lonInput = document.getElementById("lon-input");

async function loadSites() {
  const res = await fetch("/api/sites");
  const sites = await res.json();
  for (const s of sites) {
    const opt = document.createElement("option");
    opt.value = s.id;
    opt.textContent = s.name;
    opt.dataset.lat = s.lat;
    opt.dataset.lon = s.lon;
    select.append(opt);
  }
  const { site } = getState();
  if (site) select.value = site;
}

select?.addEventListener("change", () => {
  const opt = select.selectedOptions[0];
  if (!opt?.value) return;
  const lat = Number(opt.dataset.lat);
  const lon = Number(opt.dataset.lon);
  latInput.value = lat;
  lonInput.value = lon;
  setState({ site: opt.textContent, lat, lon });
});

document.getElementById("coords-apply")?.addEventListener("click", () => {
  const lat = Number(latInput.value);
  const lon = Number(lonInput.value);
  if (Number.isFinite(lat) && Number.isFinite(lon)) setState({ site: null, lat, lon });
});

// Точку можна вибрати й кліком по глобусу — поля координат показують поточний вибір.
subscribe(({ lat, lon, site }) => {
  if (lat !== null && lon !== null) {
    latInput.value = Number(lat.toFixed(4));
    lonInput.value = Number(lon.toFixed(4));
  }
  if (!site && select) select.value = "";
});

loadSites();
