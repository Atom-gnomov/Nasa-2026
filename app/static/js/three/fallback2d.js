// М16. 2D-заглушка без WebGL: рівнопроміжна карта Місяця (та сама текстура color.jpg, що й на глобусі:
// ліворуч −180°, угорі +90°), маркер вибраної точки й вибір точки кліком. Календар, оверлей метрик і
// порівняння на сторінці працюють як завжди — вони не залежать від 3D.

// Точка → частки ширини й висоти карти (0…1). Довгота нормалізується до [−180, 180).
export function latLonToFraction(lat, lon) {
  const l = ((((lon + 180) % 360) + 360) % 360) - 180;
  return { x: (l + 180) / 360, y: (90 - lat) / 180 };
}

// Частки карти → широта/довгота, округлені до 0,001° (≈ 30 м на екваторі — точніше клік не вкаже).
export function fractionToLatLon(fx, fy) {
  const clamp = (v) => Math.min(1, Math.max(0, v));
  const round = (v) => Math.round(v * 1000) / 1000;
  return { lat: round(90 - clamp(fy) * 180), lon: round(clamp(fx) * 360 - 180) };
}

export function mountFallbackMap(host, { imageUrl, message, setState, subscribe }) {
  host.replaceChildren();
  host.classList.add("fallback-2d");
  const note = document.createElement("p");
  note.className = "placeholder small";
  note.textContent = message;
  const frame = document.createElement("div");
  frame.className = "fallback-map";
  const img = document.createElement("img");
  img.src = imageUrl;
  img.alt = "Карта Місяця (рівнопроміжна проєкція, LROC WAC)";
  img.draggable = false;
  const marker = document.createElement("span");
  marker.className = "fallback-marker";
  marker.hidden = true;
  frame.append(img, marker);
  host.append(note, frame);

  frame.addEventListener("click", (ev) => {
    const r = frame.getBoundingClientRect();
    const { lat, lon } = fractionToLatLon((ev.clientX - r.left) / r.width, (ev.clientY - r.top) / r.height);
    setState({ site: null, lat, lon });
  });
  return subscribe(({ lat, lon }) => {
    marker.hidden = !(Number.isFinite(lat) && Number.isFinite(lon));
    if (marker.hidden) return;
    const { x, y } = latLonToFraction(lat, lon);
    marker.style.left = `${x * 100}%`;
    marker.style.top = `${y * 100}%`;
  });
}
