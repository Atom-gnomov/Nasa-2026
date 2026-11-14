// Модуль «Вид з поверхні» (G7, П-3): що бачить апарат у вибраній точці.
//   • Рельєф — маска горизонту з DEM LOLA (/api/horizon: найвищий кут рельєфу на кожному азимуті до 200 км).
//   • Сонце й Земля — /api/timeline (JPL DE440) за місячну добу від дати календаря; повзунок і ▶ рухають момент
//     у межах періоду, «У календар» переносить момент у спільний стан.
//   • Шляхи лежать за рельєфом, тож ділянки, сховані за горами, перекриває сама маска; диски — справжніх
//     кутових розмірів (Сонце ≈ 0,53°, Земля ≈ 1,9°), тому зручно звужувати поле зору колесом миші.
//   • «Розгортка 360°» — та сама картина на площині (азимут × кут місця); без WebGL доступна лише вона.
// Азимут — від півночі за годинниковою стрілкою; на полюсі — від меридіана 0° (docs/MATH.md, §5).
import * as THREE from "three";
import { createScene, hasWebGL } from "./three/scene.js";
import { getState, setState, subscribe } from "./state.js";
import {
  EARTH_DIAMETER_DEG, SUN_DIAMETER_DEG, compassLabels, eventText, horizonProfile, panoramaRange, skyVector, splitAtWrap,
} from "./surface_geometry.js";

const $ = (id) => document.getElementById(id);
const root = $("surface");
const HOUR_MS = 3_600_000;
const SYNODIC_MONTH_H = 29.530589 * 24; // як у calendar.js / overlay.js
const R_TERRAIN = 100, R_PATH = 105, R_BODY = 110; // шляхи й тіла — за рельєфом, щоб він їх перекривав
const SUN_RGB = "245,185,66", EARTH_RGB = "90,169,255";

const pad2 = (v) => String(v).padStart(2, "0");
const fmtMoment = (ms) => { const d = new Date(ms); return `${pad2(d.getUTCDate())}.${pad2(d.getUTCMonth() + 1)} ${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())} UTC`; };

function seriesFrom(t) {
  const anyStation = t.times.map((_, i) => t.stations.filter((s) => s.available[i]).map((s) => s.station_id));
  return {
    t: t.times.map((s) => Date.parse(s)),
    stepH: t.step_h,
    sunAz: t.sun.azimuth_deg, sun: t.sun.elevation_deg, sunVis: t.sun.visible_fraction.map((v) => v > 0),
    earthAz: t.earth.azimuth_deg, earth: t.earth.elevation_deg, earthVis: t.earth.visible_fraction.map((v) => v > 0),
    stations: anyStation,
  };
}

// ---------- 3D: очима апарата ----------
function discTexture(rgb, glow = false) {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d");
  if (glow) {
    const grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    grad.addColorStop(0, `rgba(${rgb},0.55)`);
    grad.addColorStop(1, `rgba(${rgb},0)`);
    g.fillStyle = grad;
    g.fillRect(0, 0, 128, 128);
  } else {
    g.beginPath(); g.arc(64, 64, 62, 0, 2 * Math.PI);
    g.fillStyle = `rgb(${rgb})`; g.fill();
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

const toVec3 = (az, el, r) => new THREE.Vector3(...skyVector(az, el)).multiplyScalar(r);
const sizeAt = (diamDeg, r) => 2 * r * Math.tan((diamDeg * Math.PI) / 360);

function terrainMesh(mask) {
  const { az, el } = horizonProfile(mask);
  const pos = [], col = [], idx = [];
  az.forEach((a, k) => {
    pos.push(...toVec3(a, el[k], R_TERRAIN).toArray(), ...toVec3(a, -89.9, R_TERRAIN).toArray());
    col.push(0.42, 0.42, 0.44, 0.08, 0.08, 0.09); // верх світліший — читається силует хребтів
    if (k < az.length - 1) { const b = 2 * k; idx.push(b, b + 1, b + 2, b + 1, b + 3, b + 2); }
  });
  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geom.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
  geom.setIndex(idx);
  const mesh = new THREE.Mesh(geom, new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide }));
  const ridge = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(az.map((a, k) => toVec3(a, el[k], R_TERRAIN * 0.999))),
    new THREE.LineBasicMaterial({ color: 0xc9ced8 }),
  );
  return [mesh, ridge];
}

function circleLine(el, r, color, dashed = false) {
  const pts = Array.from({ length: 361 }, (_, a) => toVec3(a, el, r));
  const geom = new THREE.BufferGeometry().setFromPoints(pts);
  const mat = dashed
    ? new THREE.LineDashedMaterial({ color, dashSize: 1.2, gapSize: 1.2, transparent: true, opacity: 0.6 })
    : new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.25 });
  const line = new THREE.Line(geom, mat);
  if (dashed) line.computeLineDistances();
  return line;
}

function pathLine(az, el, rgb) {
  const geom = new THREE.BufferGeometry().setFromPoints(az.map((a, k) => toVec3(a, el[k], R_PATH)));
  return new THREE.Line(geom, new THREE.LineBasicMaterial({ color: new THREE.Color(`rgb(${rgb})`), transparent: true, opacity: 0.75 }));
}

function create3D(host, labelsEl) {
  const ctx = createScene(host);
  if (!ctx) return null;
  const { scene, camera, renderer, controls } = ctx;
  host.append(labelsEl);
  camera.fov = 70;
  camera.near = 0.0005;
  camera.far = 1000;
  camera.updateProjectionMatrix();
  // Огляд «з місця»: камера майже в центрі, обертання навколо точки перед нею (знак — як у панорам)
  controls.enableZoom = false;
  controls.enablePan = false;
  controls.rotateSpeed = -0.35;
  controls.target.set(0, 0, 0);
  const lookAt = (az, el) => {
    camera.position.copy(toVec3(az, el, -0.001));
    controls.update();
  };
  lookAt(180, 10);
  host.addEventListener("wheel", (ev) => {
    ev.preventDefault();
    camera.fov = THREE.MathUtils.clamp(camera.fov * (ev.deltaY > 0 ? 1.12 : 1 / 1.12), 3, 100);
    camera.updateProjectionMatrix();
  }, { passive: false });

  const world = new THREE.Group();
  scene.add(world);
  const sun = new THREE.Sprite(new THREE.SpriteMaterial({ map: discTexture(SUN_RGB) }));
  const sunGlow = new THREE.Sprite(new THREE.SpriteMaterial({ map: discTexture(SUN_RGB, true), blending: THREE.AdditiveBlending, depthWrite: false }));
  const earth = new THREE.Sprite(new THREE.SpriteMaterial({ map: discTexture(EARTH_RGB) }));
  sun.scale.setScalar(sizeAt(SUN_DIAMETER_DEG, R_BODY));
  sunGlow.scale.setScalar(sizeAt(SUN_DIAMETER_DEG * 8, R_BODY));
  earth.scale.setScalar(sizeAt(EARTH_DIAMETER_DEG, R_BODY));
  scene.add(sun, sunGlow, earth);

  let labels = [];
  function setData(mask, series, lat) {
    world.traverse((o) => { o.geometry?.dispose(); o.material?.dispose(); });
    world.clear();
    world.add(...terrainMesh(mask), circleLine(0, R_TERRAIN * 1.001, 0xe6e8ee, true));
    for (const e of [30, 60]) world.add(circleLine(e, R_PATH, 0x8a92a6));
    world.add(pathLine(series.sunAz, series.sun, SUN_RGB), pathLine(series.earthAz, series.earth, EARTH_RGB));
    labels = [
      ...compassLabels(lat).map(({ az, text }) => ({ pos: toVec3(az, -2.5, R_TERRAIN), text, cls: "compass" })),
      { body: "sun", text: "Сонце", cls: "sun" },
      { body: "earth", text: "Земля", cls: "earth" },
    ];
    labelsEl.replaceChildren(...labels.map((l) => {
      const el = document.createElement("span");
      el.className = `surface-label ${l.cls}`;
      el.textContent = l.text;
      l.el = el;
      return el;
    }));
  }

  function setMoment(series, i) {
    sun.position.copy(toVec3(series.sunAz[i], series.sun[i], R_BODY));
    sunGlow.position.copy(sun.position);
    sunGlow.visible = series.sunVis[i]; // атмосфери немає: ореол лише як позначка видимого диска, не «світанок»
    earth.position.copy(toVec3(series.earthAz[i], series.earth[i], R_BODY));
    for (const l of labels) if (l.body) l.pos = (l.body === "sun" ? sun : earth).position.clone();
  }

  const v = new THREE.Vector3(), fwd = new THREE.Vector3();
  function placeLabels() {
    const { clientWidth: w, clientHeight: h } = host;
    camera.getWorldDirection(fwd);
    for (const l of labels) {
      if (!l.pos) continue;
      v.copy(l.pos);
      const front = v.clone().normalize().dot(fwd) > 0;
      v.project(camera);
      const show = front && Math.abs(v.x) <= 1.05 && Math.abs(v.y) <= 1.05;
      l.el.style.display = show ? "" : "none";
      if (show) l.el.style.transform = `translate(${((v.x + 1) / 2) * w}px, ${((1 - v.y) / 2) * h}px)`;
    }
  }

  let running = true;
  const loop = () => { controls.update(); placeLabels(); renderer.render(scene, camera); };
  renderer.setAnimationLoop(loop);
  return {
    setData, setMoment, lookAt,
    setRunning(on) { if (on !== running) { running = on; renderer.setAnimationLoop(on ? loop : null); } },
  };
}

// ---------- Розгортка 360° (2D) ----------
function drawPanorama(canvas, mask, series, i, lat) {
  const dpr = window.devicePixelRatio || 1;
  const w = Math.max(320, canvas.clientWidth), h = Math.max(200, canvas.clientHeight);
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);
  const g = canvas.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.fillStyle = "#000";
  g.fillRect(0, 0, w, h);
  g.font = "11px system-ui";
  const pad = { l: 34, r: 8, t: 8, b: 18 };
  const { min, max, step } = panoramaRange(mask, series);
  const X = (az) => pad.l + (az / 360) * (w - pad.l - pad.r);
  const Y = (el) => h - pad.b - ((el - min) / (max - min)) * (h - pad.t - pad.b);
  // Сітка кутів
  g.strokeStyle = "rgba(138,146,166,0.25)";
  g.fillStyle = "#8a92a6";
  for (let e = min; e <= max; e += step) {
    g.beginPath(); g.moveTo(pad.l, Y(e)); g.lineTo(w - pad.r, Y(e)); g.stroke();
    g.fillText(`${e}°`, 2, Y(e) + 4);
  }
  for (const { az, text } of compassLabels(lat)) g.fillText(text, Math.min(X(az) - 6, w - 60), h - 4);
  // Шляхи за місячну добу: видимі ділянки яскраві, сховані за рельєфом — тьмяні
  for (const [azs, els, vis, rgb] of [[series.sunAz, series.sun, series.sunVis, SUN_RGB], [series.earthAz, series.earth, series.earthVis, EARTH_RGB]]) {
    for (let k = 0; k < azs.length; k++) {
      if (els[k] < min || els[k] > max) continue; // нижче шкали (напр. Сонце вночі на екваторі) не малюємо
      g.fillStyle = `rgba(${rgb},${vis[k] ? 0.85 : 0.25})`;
      g.fillRect(X(azs[k]) - 1, Y(els[k]) - 1, 2, 2);
    }
  }
  // Рельєф поверх шляхів (за маскою — нічого не видно)
  const { az, el } = horizonProfile(mask);
  g.fillStyle = "#3a3d44";
  g.beginPath();
  g.moveTo(X(0), h - pad.b);
  az.forEach((a, k) => g.lineTo(X(a), Y(Math.max(min, el[k]))));
  g.lineTo(X(360), h - pad.b);
  g.closePath();
  g.fill();
  g.strokeStyle = "#c9ced8";
  g.beginPath();
  for (const [s, e] of splitAtWrap(az)) az.slice(s, e).forEach((a, k) => (k ? g.lineTo(X(a), Y(el[s + k])) : g.moveTo(X(a), Y(el[s + k]))));
  g.stroke();
  // Горизонт 0°
  g.strokeStyle = "rgba(230,232,238,0.55)"; g.setLineDash([4, 4]);
  g.beginPath(); g.moveTo(pad.l, Y(0)); g.lineTo(w - pad.r, Y(0)); g.stroke(); g.setLineDash([]);
  // Сонце й Земля в момент i (кружок трохи більший за справжній диск, щоб було видно на розгортці):
  // суцільний — тіло видно над рельєфом, кільце — сховане за маскою
  for (const [azs, els, vis, rgb] of [[series.sunAz, series.sun, series.sunVis, SUN_RGB], [series.earthAz, series.earth, series.earthVis, EARTH_RGB]]) {
    if (els[i] < min) continue;
    g.beginPath(); g.arc(X(azs[i]), Y(els[i]), 5, 0, 2 * Math.PI);
    if (vis[i]) { g.fillStyle = `rgb(${rgb})`; g.fill(); } else { g.strokeStyle = `rgb(${rgb})`; g.lineWidth = 1.5; g.stroke(); g.lineWidth = 1; }
  }
}

// ---------- Панель на сторінці ----------
if (root) {
  const host3d = $("surface-view");
  const flat = $("surface-flat");
  const slider = $("surface-time");
  const momentEl = $("surface-moment");
  const eventsEl = $("surface-events");
  const statusEl = $("surface-status");
  const playBtn = $("surface-play");
  const modeBtns = [...root.querySelectorAll("[data-surface]")];
  const labelsEl = document.createElement("div");
  labelsEl.className = "surface-labels";
  const webgl = hasWebGL();
  let mode = webgl ? "3d" : "flat";
  let view3d = null, mask = null, series = null, lat = null;
  let maskKey = null, tlKey = null, abort = null, timer = null, playing = false, visible = false;

  if (!webgl) {
    for (const b of modeBtns) if (b.dataset.surface === "3d") b.style.display = "none";
  }

  const index = () => Number(slider.value);
  function render() {
    if (!mask || !series) return;
    const i = Math.min(index(), series.t.length - 1);
    momentEl.textContent = `${fmtMoment(series.t[i])} (+${Math.round((series.t[i] - series.t[0]) / HOUR_MS)} год від дати календаря)`;
    const st = series.stations[i];
    eventsEl.textContent = [
      `Сонце: ${series.sun[i].toFixed(2)}°, ${eventText("Сонця", series.sunVis, i, series.stepH)}`,
      `Земля: ${series.earth[i].toFixed(2)}°, ${eventText("Землі", series.earthVis, i, series.stepH)}`,
      `DSN: ${st.length ? st.map((s) => s[0].toUpperCase() + s.slice(1)).join(", ") : "немає зв'язку"}`,
    ].join(" · ");
    if (mode === "3d" && view3d) view3d.setMoment(series, i);
    if (mode === "flat") drawPanorama(flat, mask, series, i, lat);
  }

  function setMode(next) {
    mode = next;
    for (const b of modeBtns) b.classList.toggle("active", b.dataset.surface === next);
    host3d.style.display = next === "3d" ? "" : "none";
    flat.style.display = next === "flat" ? "" : "none";
    for (const b of root.querySelectorAll("[data-look]")) b.disabled = next !== "3d";
    ensure3D();
    view3d?.setRunning(next === "3d" && visible);
    render();
  }

  // 3D створюється лише коли розділ уперше видно — другий WebGL-контекст не навантажує сторінку даремно
  function ensure3D() {
    if (view3d || mode !== "3d" || !visible || !mask || !series) return;
    view3d = create3D(host3d, labelsEl);
    if (!view3d) { setMode("flat"); return; }
    view3d.setData(mask, series, lat);
    lookAtBody("sun");
    render();
  }

  function lookAtBody(what) {
    if (!view3d || !series) return;
    const i = index();
    if (what === "sun") view3d.lookAt(series.sunAz[i], Math.max(series.sun[i], 2));
    else if (what === "earth") view3d.lookAt(series.earthAz[i], Math.max(series.earth[i], 2));
    else view3d.lookAt(Number(what), 5);
  }

  async function load({ lat: la, lon, datetime, height_m: height = 0 }) {
    if (la == null || lon == null) {
      statusEl.textContent = "Виберіть місце на Місяці — вид з поверхні покаже горизонт і рух Сонця й Землі.";
      return;
    }
    const point = { lat: la, lon };
    if (height) point.height = height;
    const mKey = JSON.stringify(point);
    const tKey = `${mKey}|${datetime}`;
    if (mKey === maskKey && tKey === tlKey) return;
    abort?.abort();
    abort = new AbortController();
    const end = new Date(Date.parse(datetime) + SYNODIC_MONTH_H * HOUR_MS).toISOString().slice(0, 16) + "Z";
    statusEl.textContent = "Рахую горизонт і шляхи Сонця й Землі…";
    const get = async (url) => {
      const res = await fetch(url, { signal: abort.signal });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || res.statusText);
      return body;
    };
    try {
      const [m, t] = await Promise.all([
        mKey === maskKey ? mask : get(`/api/horizon?${new URLSearchParams(point)}`),
        get(`/api/timeline?${new URLSearchParams({ ...point, start: datetime, end, step_h: 1 })}`),
      ]);
      mask = m; series = seriesFrom(t); lat = la;
      maskKey = mKey; tlKey = tKey;
      slider.max = String(series.t.length - 1);
      slider.value = "0";
      const src = m.source === "flat" ? "гладка сфера (немає DEM для цієї точки)" : `LOLA ${m.source.toUpperCase()}`;
      statusEl.textContent = `Рельєф: ${src}, промені до ${m.max_distance_km ?? 200} км, найвища точка горизонту ` +
        `${(m.max_elevation_deg ?? Math.max(...m.elevations_deg)).toFixed(1)}°, відкрите небо ${Math.round(m.sky_view_fraction * 100)} %. ` +
        `Азимут — від півночі за годинниковою стрілкою${Math.abs(la) > 89.999 ? " (на полюсі — від меридіана 0°)" : ""}. ` +
        `Колесо миші — поле зору; диски Сонця й Землі — справжнього кутового розміру.`;
      view3d?.setData(mask, series, lat);
      ensure3D();
      render();
    } catch (err) {
      if (err.name === "AbortError") return;
      maskKey = tlKey = null;
      statusEl.textContent = `Вид з поверхні недоступний: ${err.message}`;
    }
  }

  slider.addEventListener("input", render);
  for (const b of modeBtns) b.addEventListener("click", () => setMode(b.dataset.surface));
  for (const b of root.querySelectorAll("[data-look]")) b.addEventListener("click", () => lookAtBody(b.dataset.look));
  $("surface-to-calendar").addEventListener("click", () => {
    if (series) setState({ datetime: new Date(series.t[index()]).toISOString().slice(0, 16) + "Z" });
  });
  let lastTick = 0;
  const tick = (now) => {
    if (!playing) return;
    if (now - lastTick > 40) { // ≈ 25 год періоду за секунду
      lastTick = now;
      slider.value = String((index() + 1) % (Number(slider.max) + 1));
      render();
    }
    requestAnimationFrame(tick);
  };
  playBtn.addEventListener("click", () => {
    playing = !playing;
    playBtn.textContent = playing ? "⏸" : "▶";
    if (playing) requestAnimationFrame(tick);
  });
  new ResizeObserver(() => { if (mode === "flat") render(); }).observe(flat);
  new IntersectionObserver(([e]) => {
    visible = e.isIntersecting;
    ensure3D();
    view3d?.setRunning(mode === "3d" && visible);
  }).observe(root);

  setMode(mode);
  subscribe((st) => { clearTimeout(timer); timer = setTimeout(() => load(st), 300); });
}
