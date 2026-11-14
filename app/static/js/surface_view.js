// Модуль «Вид з поверхні» (G7, П-3): що бачить апарат у вибраній точці.
//   • Поверхня довкола — сітка висот з DEM LOLA (/api/terrain: 20 м біля південного полюса, до 474 м деінде),
//     освітлена справжнім Сонцем на момент (закон Ламберта за нормаллю з DEM) із геометричними тінями за рельєфом.
//   • Далі за ділянкою — силует горизонту за маскою рельєфу (/api/horizon, промені до 200 км).
//   • Сонце й Земля — /api/timeline (JPL DE440) за місячну добу від дати календаря; диски справжніх кутових
//     розмірів, фаза Землі — з геометрії Сонце–Земля на небі місця; повзунок і ▶ рухають момент.
//   • Режими: «3D: очима апарата» (Three.js), «Панорама» (canvas 2D, обертання й масштаб; працює без WebGL),
//     «Розгортка 360°» (азимут × кут місця — оглядова схема шляхів).
// Азимут — від півночі за годинниковою стрілкою; на полюсі — від меридіана 0° (docs/MATH.md, §5).
// Висота камери (2 м) — лише для вигляду; вертикальне перебільшення рельєфу вмикає користувач і підписане.
import * as THREE from "three";
import { createScene, hasWebGL } from "./three/scene.js";
import { qualitySettings } from "./three/quality.js";
import { onLangChange, t } from "./i18n.js";
import { getState, setState, subscribe } from "./state.js";
import {
  EARTH_DIAMETER_DEG, SUN_DIAMETER_DEG, compassLabels, eventText, horizonProfile, panoramaRange, skyVector, splitAtWrap,
} from "./surface_geometry.js";
import { R_MOON_M, earthPhase, lightGrid, makePatch, renderTerrain, shadeGray, slopeFill } from "./surface_terrain.js";

const $ = (id) => document.getElementById(id);
const root = $("surface");
const HOUR_MS = 3_600_000;
const SYNODIC_MONTH_H = 29.530589 * 24; // як у calendar.js / overlay.js
const EYE_M = 2; // висота камери над ґрунтом, м (візуальний параметр)
const R_RING = 100, R_PATH = 105, R_BODY = 110; // дальній силует, шляхи й тіла (3D); шляхи за рельєфом
const SUN_RGB = "245,185,66", EARTH_RGB = "90,169,255";
const RINGS_M = [5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000]; // кільця дальності на панорамі
const DEG = Math.PI / 180;

const pad2 = (v) => String(v).padStart(2, "0");
const fmtMoment = (ms) => { const d = new Date(ms); return `${pad2(d.getUTCDate())}.${pad2(d.getUTCMonth() + 1)} ${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())} UTC`; };
const wrap180 = (d) => ((((d + 180) % 360) + 360) % 360) - 180;
const dayMonth = (ms) => { const d = new Date(ms); return `${pad2(d.getUTCDate())}.${pad2(d.getUTCMonth() + 1)}`; };

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

// ---------- Малювання Сонця й Землі (спільне для 2D і 3D) ----------
// Земля з фазою: темний диск + освітлена частина (півколо + півеліпс термінатора), повернута до Сонця.
function drawEarthDisc(g, cx, cy, r, ph) {
  g.save();
  g.translate(cx, cy);
  g.rotate(ph.bearing * DEG);
  g.beginPath(); g.arc(0, 0, r, 0, 2 * Math.PI); g.fillStyle = "rgb(18,32,58)"; g.fill();
  if (ph.fraction > 0.003) {
    const yt = r * (2 * ph.fraction - 1); // термінатор: −r (нова) … 0 (півдиска) … +r (повна)
    g.beginPath();
    g.moveTo(-r, 0);
    g.arc(0, 0, r, Math.PI, 2 * Math.PI);
    g.ellipse(0, 0, r, Math.max(Math.abs(yt), 1e-4), 0, 0, Math.PI, yt < 0);
    g.closePath();
    g.fillStyle = `rgb(${EARTH_RGB})`;
    g.fill();
  }
  g.restore();
}

function drawSunDisc(g, cx, cy, r) {
  const glow = g.createRadialGradient(cx, cy, r * 0.5, cx, cy, r * 6);
  glow.addColorStop(0, `rgba(${SUN_RGB},0.45)`);
  glow.addColorStop(1, `rgba(${SUN_RGB},0)`);
  g.fillStyle = glow;
  g.beginPath(); g.arc(cx, cy, r * 6, 0, 2 * Math.PI); g.fill();
  g.fillStyle = "#ffe9b0";
  g.beginPath(); g.arc(cx, cy, r, 0, 2 * Math.PI); g.fill();
}

// ---------- 3D: очима апарата ----------
const toVec3 = (az, el, r) => new THREE.Vector3(...skyVector(az, el)).multiplyScalar(r);
const sizeAt = (diamDeg, r) => 2 * r * Math.tan((diamDeg * Math.PI) / 360);

// Дальній силует за маскою: стіна на R_RING від кута маски до надира; сірий колір — освітленість далекої землі.
function ringMesh(mask, gray) {
  const { az, el } = horizonProfile(mask);
  const pos = [], col = [], idx = [];
  az.forEach((a, k) => {
    pos.push(...toVec3(a, el[k], R_RING).toArray(), ...toVec3(a, -89.9, R_RING).toArray());
    col.push(gray, gray, gray, gray * 0.3, gray * 0.3, gray * 0.3);
    if (k < az.length - 1) { const b = 2 * k; idx.push(b, b + 1, b + 2, b + 1, b + 3, b + 2); }
  });
  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geom.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
  geom.setIndex(idx);
  const mesh = new THREE.Mesh(geom, new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide }));
  const ridge = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(az.map((a, k) => toVec3(a, el[k], R_RING * 0.999))),
    new THREE.LineBasicMaterial({ color: 0xc9ced8 }),
  );
  return [mesh, ridge];
}

// Сітка поверхні в справжній геометрії (з кривиною); колір вершини — освітленість з lightGrid.
function patchMesh(patch, unit) {
  const { n, s, c, h } = patch;
  const rmax = patch.half * 0.98;
  const pos = new Float32Array(n * n * 3), col = new Float32Array(n * n * 3), idx = [];
  const inside = (i, j) => Math.hypot((j - c) * s, (i - c) * s) <= rmax;
  for (let i = 0; i < n - 1; i++) {
    for (let j = 0; j < n - 1; j++) {
      if (!inside(i, j) || !inside(i + 1, j + 1) || !inside(i, j + 1) || !inside(i + 1, j)) continue;
      const a = i * n + j;
      idx.push(a, a + 1, a + n, a + 1, a + n + 1, a + n);
    }
  }
  const geom = new THREE.BufferGeometry();
  const posAttr = new THREE.BufferAttribute(pos, 3), colAttr = new THREE.BufferAttribute(col, 3);
  geom.setAttribute("position", posAttr);
  geom.setAttribute("color", colAttr);
  geom.setIndex(new THREE.BufferAttribute(Uint32Array.from(idx), 1));
  const mesh = new THREE.Mesh(geom, new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide }));
  mesh.frustumCulled = false;
  return {
    mesh,
    setHeights(exag) {
      const R = R_MOON_M;
      for (let i = 0; i < n; i++) {
        for (let j = 0; j < n; j++) {
          const k = i * n + j, e = (j - c) * s, nn = (i - c) * s, rho = Math.hypot(e, nn, R), rs = R + h[k] * exag;
          pos[3 * k] = (rs * e) / rho / unit;
          pos[3 * k + 1] = ((rs * R) / rho - R) / unit;
          pos[3 * k + 2] = -(rs * nn) / rho / unit;
        }
      }
      posAttr.needsUpdate = true;
    },
    setLight(light, ambient, fill) {
      for (let k = 0; k < n * n; k++) {
        const g = shadeGray(light ? light[k] : 0, ambient, fill ? fill[k] : 1) / 255;
        col[3 * k] = col[3 * k + 1] = col[3 * k + 2] = g;
      }
      colAttr.needsUpdate = true;
    },
  };
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
  controls.enableZoom = false;
  controls.enablePan = false;
  controls.rotateSpeed = -0.35;
  let eyeY = EYE_M / 52;
  const lookAt = (az, el) => {
    controls.target.set(0, eyeY, 0);
    camera.position.copy(controls.target).add(toVec3(az, el, -0.001));
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
  const sun = new THREE.Sprite(new THREE.SpriteMaterial({ map: null }));
  const sunCanvas = document.createElement("canvas");
  sunCanvas.width = sunCanvas.height = 128;
  drawSunDisc(sunCanvas.getContext("2d"), 64, 64, 10);
  const sunTex = new THREE.CanvasTexture(sunCanvas);
  sunTex.colorSpace = THREE.SRGBColorSpace;
  sun.material.map = sunTex;
  const earthCanvas = document.createElement("canvas");
  earthCanvas.width = earthCanvas.height = 128;
  const earthTex = new THREE.CanvasTexture(earthCanvas);
  earthTex.colorSpace = THREE.SRGBColorSpace;
  const earth = new THREE.Sprite(new THREE.SpriteMaterial({ map: earthTex, transparent: true }));
  // спрайт Сонця містить ореол (радіус диска 10 з 64 пікселів): масштабуємо так, щоб диск мав справжній розмір
  sun.scale.setScalar(sizeAt(SUN_DIAMETER_DEG, R_BODY) * (64 / 10));
  earth.scale.setScalar(sizeAt(EARTH_DIAMETER_DEG, R_BODY) * (128 / 100));
  scene.add(sun, earth);

  let labels = [], mesh = null, ring = null, unit = 52;
  function setData(mask, series, lat, patch, exag) {
    world.traverse((o) => { o.geometry?.dispose(); o.material?.dispose(); });
    world.clear();
    unit = (patch ? patch.half * 0.98 : 5000) / 95;
    eyeY = EYE_M / unit;
    ring = ringMesh(mask, 0.32);
    world.add(...ring, circleLine(0, R_RING * 1.001, 0xe6e8ee, true));
    mesh = patch ? patchMesh(patch, unit) : null;
    if (mesh) { mesh.setHeights(exag); mesh.setLight(null, 0.03, null); world.add(mesh.mesh); }
    for (const e of [30, 60]) world.add(circleLine(e, R_PATH, 0x8a92a6));
    world.add(pathLine(series.sunAz, series.sun, SUN_RGB), pathLine(series.earthAz, series.earth, EARTH_RGB));
    labels = [
      ...compassLabels(lat).map(({ az, text }) => ({ pos: toVec3(az, -2.5, R_RING), text, cls: "compass" })),
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
    earth.position.copy(toVec3(series.earthAz[i], series.earth[i], R_BODY));
    const g = earthCanvas.getContext("2d");
    g.clearRect(0, 0, 128, 128);
    drawEarthDisc(g, 64, 64, 50, earthPhase(series.sunAz[i], series.sun[i], series.earthAz[i], series.earth[i]));
    earthTex.needsUpdate = true;
    for (const l of labels) if (l.body) l.pos = (l.body === "sun" ? sun : earth).position.clone();
  }

  const v = new THREE.Vector3(), fwd = new THREE.Vector3();
  function placeLabels() {
    const { clientWidth: w, clientHeight: h } = host;
    camera.getWorldDirection(fwd);
    for (const l of labels) {
      if (!l.pos) continue;
      v.copy(l.pos);
      const front = v.clone().sub(camera.position).normalize().dot(fwd) > 0;
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
    setLight(light, farGray, ambient, fill) { mesh?.setLight(light, ambient, fill); if (ring) ring[0].material.color.setScalar(farGray); },
    setExag(exag) { mesh?.setHeights(exag); },
    setRunning(on) { if (on !== running) { running = on; renderer.setAnimationLoop(on ? loop : null); } },
  };
}

// ---------- 2D: спільне ----------
const niceStep = (span, list) => list.find((s) => s >= span / 6) ?? list.at(-1);

function drawBodyLabel(g, text, x, y, rgb, scale) {
  g.font = `${12 * scale}px system-ui`;
  g.fillStyle = `rgb(${rgb})`;
  g.shadowColor = "#000"; g.shadowBlur = 3 * scale;
  g.fillText(text, x + 8 * scale, y - 8 * scale);
  g.shadowBlur = 0;
}

// ---------- Панорама (canvas 2D) з обертанням і масштабом ----------
function createPanorama(canvas) {
  const layer = document.createElement("canvas");
  let imageData = null, px = null;
  const view = { az: 180, el: 6, fov: 100 };

  function geometry() {
    const scale = Math.min(window.devicePixelRatio || 1, 1.5);
    const W = Math.max(320, Math.round(canvas.clientWidth * scale)), H = Math.max(200, Math.round(canvas.clientHeight * scale));
    if (canvas.width !== W || canvas.height !== H) { canvas.width = W; canvas.height = H; }
    return { W, H, scale, ppd: W / view.fov };
  }

  function draw(d) {
    const { mask, series, i, lat, patch, light, exag, ambient, fill, rings, sunUp } = d;
    const { W, H, scale, ppd } = geometry();
    const g = canvas.getContext("2d");
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.fillStyle = "#000";
    g.fillRect(0, 0, W, H);
    const xOf = (az) => W / 2 + wrap180(az - view.az) * ppd;
    const yOf = (el) => H / 2 - (el - view.el) * ppd;

    // 1. шляхи за місячну добу з мітками діб (за рельєфом: нижче горизонту їх закриє земля)
    g.lineWidth = 1.2 * scale;
    for (const [azs, els, vis, rgb] of [[series.sunAz, series.sun, series.sunVis, SUN_RGB], [series.earthAz, series.earth, series.earthVis, EARTH_RGB]]) {
      for (let k = 1; k < azs.length; k++) {
        const x0 = xOf(azs[k - 1]), x1 = xOf(azs[k]);
        if (Math.abs(x1 - x0) > W / 2) continue; // перехід через межу ±180° від центра кадру
        g.strokeStyle = `rgba(${rgb},${vis[k] ? 0.8 : 0.3})`;
        g.beginPath(); g.moveTo(x0, yOf(els[k - 1])); g.lineTo(x1, yOf(els[k])); g.stroke();
      }
      if (view.fov <= 200) {
        g.font = `${10 * scale}px system-ui`;
        for (let k = 0; k < azs.length; k += Math.round(24 / series.stepH)) {
          const x = xOf(azs[k]), y = yOf(els[k]);
          if (x < 0 || x > W || y < 0 || y > H) continue;
          g.fillStyle = `rgba(${rgb},0.9)`;
          g.beginPath(); g.arc(x, y, 2.2 * scale, 0, 2 * Math.PI); g.fill();
          if (rgb === SUN_RGB) g.fillText(dayMonth(series.t[k]), x + 4 * scale, y + 12 * scale);
        }
      }
    }
    // 2. Сонце й Земля в момент i (диски справжнього розміру, але не менші за позначку)
    const ph = earthPhase(series.sunAz[i], series.sun[i], series.earthAz[i], series.earth[i]);
    const sx = xOf(series.sunAz[i]), sy = yOf(series.sun[i]);
    const ex = xOf(series.earthAz[i]), ey = yOf(series.earth[i]);
    drawSunDisc(g, sx, sy, Math.max((SUN_DIAMETER_DEG / 2) * ppd, 4 * scale));
    drawEarthDisc(g, ex, ey, Math.max((EARTH_DIAMETER_DEG / 2) * ppd, 6 * scale), ph);
    drawBodyLabel(g, t("Сонце"), sx, sy, SUN_RGB, scale);
    drawBodyLabel(g, t("Земля (освітлено {p} %)", { p: Math.round(ph.fraction * 100) }), ex, ey, EARTH_RGB, scale);

    // 3. поверхня: DEM довкола + силует за маскою; закриває все, що нижче рельєфу
    if (!imageData || imageData.width !== W || imageData.height !== H) {
      layer.width = W; layer.height = H;
      imageData = new ImageData(W, H);
      px = new Uint32Array(imageData.data.buffer);
    }
    const { ringRows } = renderTerrain(patch, light, {
      pixels: px, rings: rings ? RINGS_M : null, width: W, height: H, viewAz: view.az, viewEl: view.el, fov: view.fov,
      eye: EYE_M, exag, mask, ambient, fill, farLight: sunUp ? Math.max(0, Math.sin(Math.max(series.sun[i], 0) * DEG)) * 0.55 : 0,
    });
    layer.getContext("2d").putImageData(imageData, 0, 0);
    g.drawImage(layer, 0, 0);
    g.font = `${10 * scale}px system-ui`; g.fillStyle = "rgba(190,190,190,0.95)";
    let lastY = -99;
    for (const { d: dist, y } of [...ringRows].sort((a, b) => b.y - a.y)) {
      if (lastY - y < 12 * scale) continue; // не накладаємо підписи
      g.fillText(dist >= 1000 ? `${dist / 1000} км` : `${dist} м`, W / 2 + 6 * scale, y - 2 * scale);
      lastY = y;
    }

    // 4. рулетки: горизонт 0°, кути місця зліва, азимути знизу
    g.strokeStyle = "rgba(230,232,238,0.4)"; g.setLineDash([4 * scale, 4 * scale]); g.lineWidth = scale;
    g.beginPath(); g.moveTo(0, yOf(0)); g.lineTo(W, yOf(0)); g.stroke(); g.setLineDash([]);
    g.font = `${10 * scale}px system-ui`; g.fillStyle = "#8a92a6";
    const vStep = niceStep(H / ppd, [1, 2, 5, 10, 15, 30]);
    for (let e = Math.ceil((view.el - H / 2 / ppd) / vStep) * vStep; e <= view.el + H / 2 / ppd; e += vStep) {
      g.fillText(`${e}°`, 3 * scale, yOf(e) - 2 * scale);
    }
    const hStep = niceStep(view.fov, [1, 5, 10, 15, 30, 45]);
    const names = new Map(compassLabels(lat).map((l) => [l.az, t(l.text)]));
    for (let a = Math.ceil((view.az - view.fov / 2) / hStep) * hStep; a <= view.az + view.fov / 2; a += hStep) {
      const az = ((a % 360) + 360) % 360, x = xOf(az);
      g.fillStyle = "rgba(138,146,166,0.9)";
      g.fillRect(x, H - 14 * scale, 1, 5 * scale);
      g.fillText(names.get(az) ?? `${az}°`, x + 3 * scale, H - 3 * scale);
    }
    return { sx, sy, ex, ey };
  }

  return {
    view, draw,
    ppd: () => geometry().ppd / geometry().scale, // пікселів CSS на градус
    zoom(factor) { view.fov = Math.min(360, Math.max(4, view.fov * factor)); },
    pan(dxDeg, dyDeg) { view.az = ((view.az + dxDeg) % 360 + 360) % 360; view.el = Math.max(-60, Math.min(85, view.el + dyDeg)); },
    look(az, el) { view.az = az; view.el = el; },
  };
}

// ---------- Розгортка 360° (оглядова схема) ----------
function drawUnwrapped(canvas, mask, series, i, lat) {
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
  g.strokeStyle = "rgba(138,146,166,0.25)";
  g.fillStyle = "#8a92a6";
  for (let e = Math.ceil(min / step) * step; e <= max; e += step) {
    g.beginPath(); g.moveTo(pad.l, Y(e)); g.lineTo(w - pad.r, Y(e)); g.stroke();
    g.fillText(`${e}°`, 2, Y(e) + 4);
  }
  for (const { az, text } of compassLabels(lat)) g.fillText(t(text), Math.min(X(az) - 6, w - 60), h - 4);
  // шляхи ламаною: видимі ділянки яскраві, сховані за рельєфом — тьмяні; розрив на 360° → 0°
  g.lineWidth = 1.5;
  for (const [azs, els, vis, rgb] of [[series.sunAz, series.sun, series.sunVis, SUN_RGB], [series.earthAz, series.earth, series.earthVis, EARTH_RGB]]) {
    for (const [a, b] of splitAtWrap(azs)) {
      for (let k = a + 1; k < b; k++) {
        if (els[k] < min && els[k - 1] < min) continue;
        g.strokeStyle = `rgba(${rgb},${vis[k] ? 0.9 : 0.3})`;
        g.beginPath(); g.moveTo(X(azs[k - 1]), Y(els[k - 1])); g.lineTo(X(azs[k]), Y(els[k])); g.stroke();
      }
    }
  }
  const { az, el } = horizonProfile(mask);
  g.fillStyle = "#3a3d44";
  g.beginPath();
  g.moveTo(X(0), h - pad.b);
  az.forEach((a, k) => g.lineTo(X(a), Y(Math.max(min, el[k]))));
  g.lineTo(X(360), h - pad.b);
  g.closePath();
  g.fill();
  g.strokeStyle = "#c9ced8";
  g.lineWidth = 1;
  g.beginPath();
  for (const [s, e] of splitAtWrap(az)) az.slice(s, e).forEach((a, k) => (k ? g.lineTo(X(a), Y(el[s + k])) : g.moveTo(X(a), Y(el[s + k]))));
  g.stroke();
  g.strokeStyle = "rgba(230,232,238,0.55)"; g.setLineDash([4, 4]);
  g.beginPath(); g.moveTo(pad.l, Y(0)); g.lineTo(w - pad.r, Y(0)); g.stroke(); g.setLineDash([]);
  const ph = earthPhase(series.sunAz[i], series.sun[i], series.earthAz[i], series.earth[i]);
  if (series.sun[i] >= min) drawSunDisc(g, X(series.sunAz[i]), Y(series.sun[i]), 5);
  if (series.earth[i] >= min) drawEarthDisc(g, X(series.earthAz[i]), Y(series.earth[i]), 7, ph);
}

// ---------- Панель на сторінці ----------
if (root) {
  const host3d = $("surface-view");
  const pano = $("surface-pano");
  const flat = $("surface-flat");
  const slider = $("surface-time");
  const momentEl = $("surface-moment");
  const eventsEl = $("surface-events");
  const statusEl = $("surface-status");
  const playBtn = $("surface-play");
  const exagInput = $("surface-exag");
  const exagOut = $("surface-exag-value");
  const shadowsInput = $("surface-shadows");
  const ambientInput = $("surface-ambient");
  const ringsInput = $("surface-rings");
  const modeBtns = [...root.querySelectorAll("[data-surface]")];
  const labelsEl = document.createElement("div");
  labelsEl.className = "surface-labels";
  const webgl = hasWebGL();
  let mode = webgl ? "3d" : "pano";
  const panorama = createPanorama(pano);
  let view3d = null, mask = null, series = null, patch = null, lat = null, light = null, lightKey = "";
  let maskKey = null, tlKey = null, terrainKey = null, abort = null, timer = null, shadowTimer = null;
  let playing = false, visible = false, drawQueued = false;

  if (!webgl) for (const b of modeBtns) if (b.dataset.surface === "3d") b.style.display = "none";

  const index = () => Math.min(Number(slider.value), series ? series.t.length - 1 : 0);
  const exag = () => Number(exagInput.value);

  // Освітлення: Ламберт — одразу; тіні (промінь до Сонця по DEM) — після паузи й не під час відтворення
  function updateLight(i, shadows) {
    if (!patch || !series) { light = null; return; }
    const key = `${patch.api.lat},${patch.api.lon},${patch.n}|${i}|${shadows}`;
    if (key === lightKey) return;
    lightKey = key;
    light = lightGrid(patch, series.sunAz[i], series.sun[i], { shadows, stride: patch.n > 151 ? 2 : 1 });
    view3d?.setLight(light, farGray(i), ambient(), fillGrid());
  }
  const farGray = (i) => (series.sun[i] > 0 ? 0.08 + 0.45 * Math.sin(series.sun[i] * DEG) : 0.02);
  // Умовна підсвітка тіней: без неї ніч і тіні повністю чорні (земне сяйво ≪ 1 % денного світла)
  const ambient = () => (ambientInput.checked ? 0.2 : 0.02);
  const fillGrid = () => (patch && ambientInput.checked ? slopeFill(patch) : null);

  function requestDraw() {
    if (drawQueued) return;
    drawQueued = true;
    const run = () => { if (!drawQueued) return; drawQueued = false; drawActive(); };
    requestAnimationFrame(run);
    setTimeout(run, 80); // у прихованій панелі браузера rAF не спрацьовує
  }

  function drawActive() {
    if (!mask || !series) return;
    const i = index();
    if (mode === "pano") {
      panorama.draw({ mask, series, i, lat, patch, light, exag: exag(), ambient: ambient(), fill: fillGrid(), rings: ringsInput.checked, sunUp: series.sun[i] > 0 });
    } else if (mode === "flat") {
      drawUnwrapped(flat, mask, series, i, lat);
    }
  }

  function render() {
    if (!mask || !series) return;
    const i = index();
    const hours = Math.round((series.t[i] - series.t[0]) / HOUR_MS);
    momentEl.textContent = `${fmtMoment(series.t[i])} ${t("(+{n} год від дати календаря)", { n: hours })}`;
    const st = series.stations[i];
    const ph = earthPhase(series.sunAz[i], series.sun[i], series.earthAz[i], series.earth[i]);
    eventsEl.textContent = [
      `Сонце: ${series.sun[i].toFixed(2)}°, ${eventText("Сонця", series.sunVis, i, series.stepH)}`,
      `Земля: ${series.earth[i].toFixed(2)}°, освітлено ${Math.round(ph.fraction * 100)} %, ${eventText("Землі", series.earthVis, i, series.stepH)}`,
      `DSN: ${st.length ? st.map((s) => s[0].toUpperCase() + s.slice(1)).join(", ") : "немає зв'язку"}`,
    ].join(" · ");
    updateLight(i, false);
    clearTimeout(shadowTimer);
    if (shadowsInput.checked && !playing && patch) shadowTimer = setTimeout(() => { updateLight(i, true); requestDraw(); }, 140);
    view3d?.setMoment(series, i);
    requestDraw();
  }

  function setMode(next) {
    mode = next;
    for (const b of modeBtns) b.classList.toggle("active", b.dataset.surface === next);
    host3d.style.display = next === "3d" ? "" : "none";
    pano.style.display = next === "pano" ? "" : "none";
    flat.style.display = next === "flat" ? "" : "none";
    for (const b of root.querySelectorAll("[data-look], [data-zoom]")) b.disabled = next === "flat";
    ensure3D();
    view3d?.setRunning(next === "3d" && visible);
    requestDraw();
  }

  // 3D створюється лише коли розділ уперше видно — другий WebGL-контекст не навантажує сторінку даремно
  function ensure3D() {
    if (view3d || mode !== "3d" || !visible || !mask || !series) return;
    view3d = create3D(host3d, labelsEl);
    if (!view3d) { setMode("pano"); return; }
    view3d.setData(mask, series, lat, patch, exag());
    lookAtBody("sun");
    lightKey = "";
    render();
  }

  function lookAtBody(what) {
    if (!series) return;
    const i = index();
    let az, el;
    if (what === "sun") { az = series.sunAz[i]; el = series.sun[i]; }
    else if (what === "earth") { az = series.earthAz[i]; el = series.earth[i]; }
    else { az = Number(what); el = 4; }
    const aspect = pano.clientHeight / Math.max(pano.clientWidth, 1);
    const body = what === "sun" || what === "earth";
    // високе тіло: розширюємо поле зору (до 200°), щоб і воно, і горизонт лишалися в кадрі
    if (body && el > 0 && (el + 8) / aspect > panorama.view.fov) panorama.view.fov = Math.min(200, (el + 8) / aspect);
    const vspan = panorama.view.fov * aspect;
    // тіло — у верхній частині кадру, щоб лишалась видимою земля під ним; горизонт — у нижній третині
    const centerEl = body ? Math.min(Math.max(0.2 * vspan, el - 0.25 * vspan), vspan / 2 - 3) : 0.2 * vspan;
    panorama.look(az, centerEl);
    view3d?.lookAt(az, Math.max(el, 2));
    requestDraw();
  }

  // Опис рельєфу — речення-шаблони з підстановкою: так їх можна перекласти (i18n.js), а не склеювати з уламків
  function renderStatus() {
    if (!mask) return;
    const m = mask, a = patch?.api;
    const src = m.source === "flat" ? t("гладка сфера (немає DEM для цієї точки)") : `LOLA ${m.source.toUpperCase()}`;
    const pat = !patch ? t("поверхня довкола недоступна — лише силует горизонту")
      : a.source === "flat" ? t("поверхня довкола: гладка сфера (немає DEM)")
        : t("поверхня довкола: LOLA {src}, крок {step} м, радіус {r} км (відносно точки {lo}…+{hi} м)",
          { src: a.source.toUpperCase(), step: a.spacing_m.toFixed(0), r: a.radius_km, lo: a.min_height_m.toFixed(0), hi: a.max_height_m.toFixed(0) });
    const pole = Math.abs(lat) > 89.999 ? ` ${t("(на полюсі — від меридіана 0°)")}` : "";
    statusEl.textContent = [
      t("Рельєф: {src}; {pat}.", { src, pat }),
      t("Далі — силует за маскою до {d} км, найвища точка горизонту {max}°, відкрите небо {sky} %.",
        { d: m.max_distance_km ?? 200, max: (m.max_elevation_deg ?? Math.max(...m.elevations_deg)).toFixed(1), sky: Math.round(m.sky_view_fraction * 100) }),
      t("Яскравість умовна, тіні — геометричні, з DEM (за межами ділянки не враховано); камера на висоті {eye} м — лише для вигляду.", { eye: EYE_M }),
      t("Азимут — від півночі за годинниковою стрілкою{pole}.", { pole }),
      t("Перетягування — повернути, колесо — масштаб."),
    ].join(" ");
  }

  async function load({ lat: la, lon, datetime, height_m: height = 0 }) {
    if (la == null || lon == null) {
      statusEl.textContent = "Виберіть місце на Місяці — вид з поверхні покаже горизонт і рух Сонця й Землі.";
      return;
    }
    const point = { lat: la, lon };
    if (height) point.height = height;
    const mKey = JSON.stringify(point);
    const pKey = `${la},${lon}`;
    const tKey = `${mKey}|${datetime}`;
    if (mKey === maskKey && tKey === tlKey && pKey === terrainKey) return;
    abort?.abort();
    abort = new AbortController();
    const end = new Date(Date.parse(datetime) + SYNODIC_MONTH_H * HOUR_MS).toISOString().slice(0, 16) + "Z";
    statusEl.textContent = "Рахую горизонт, поверхню та шляхи Сонця й Землі…";
    const get = async (url) => {
      const res = await fetch(url, { signal: abort.signal });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || res.statusText);
      return body;
    };
    const getOptional = async (url) => {
      try { return await get(url); } catch (err) { if (err.name === "AbortError") throw err; return null; }
    };
    const terrainQuery = new URLSearchParams({ lat: la, lon });
    const q = qualitySettings();
    if (q.terrainN) terrainQuery.set("n", q.terrainN);
    try {
      const [m, t, tr] = await Promise.all([
        mKey === maskKey ? mask : get(`/api/horizon?${new URLSearchParams(point)}`),
        get(`/api/timeline?${new URLSearchParams({ ...point, start: datetime, end, step_h: 1 })}`),
        pKey === terrainKey ? patch : getOptional(`/api/terrain?${terrainQuery}`).then((r) => (r ? makePatch(r) : null)),
      ]);
      const newPlace = mKey !== maskKey || pKey !== terrainKey;
      mask = m; series = seriesFrom(t); lat = la; patch = tr;
      maskKey = mKey; tlKey = tKey; terrainKey = pKey; lightKey = "";
      slider.max = String(series.t.length - 1);
      slider.value = "0";
      renderStatus();
      view3d?.setData(mask, series, lat, patch, exag());
      if (newPlace) lookAtBody(series.sun[0] > -2 ? "sun" : "earth");
      ensure3D();
      render();
    } catch (err) {
      if (err.name === "AbortError") return;
      maskKey = tlKey = terrainKey = null;
      statusEl.textContent = `Вид з поверхні недоступний: ${err.message}`;
    }
  }

  // Керування: повзунок часу, режими, «дивитися на», масштаб, перетягування й колесо на панорамі
  slider.addEventListener("input", render);
  for (const b of modeBtns) b.addEventListener("click", () => setMode(b.dataset.surface));
  for (const b of root.querySelectorAll("[data-look]")) b.addEventListener("click", () => lookAtBody(b.dataset.look));
  for (const b of root.querySelectorAll("[data-zoom]")) {
    b.addEventListener("click", () => { panorama.zoom(b.dataset.zoom === "in" ? 1 / 1.4 : 1.4); requestDraw(); });
  }
  exagInput.addEventListener("input", () => {
    exagOut.textContent = exagInput.value;
    view3d?.setExag(exag());
    requestDraw();
  });
  shadowsInput.addEventListener("change", () => { lightKey = ""; render(); });
  ambientInput.addEventListener("change", () => { lightKey = ""; render(); });
  ringsInput.addEventListener("change", requestDraw);
  $("surface-to-calendar").addEventListener("click", () => {
    if (series) setState({ datetime: new Date(series.t[index()]).toISOString().slice(0, 16) + "Z" });
  });
  let drag = null;
  pano.addEventListener("pointerdown", (ev) => { drag = { x: ev.clientX, y: ev.clientY }; pano.setPointerCapture(ev.pointerId); pano.style.cursor = "grabbing"; });
  pano.addEventListener("pointermove", (ev) => {
    if (!drag) return;
    const ppd = panorama.ppd();
    panorama.pan(-(ev.clientX - drag.x) / ppd, (ev.clientY - drag.y) / ppd);
    drag = { x: ev.clientX, y: ev.clientY };
    requestDraw();
  });
  const endDrag = () => { drag = null; pano.style.cursor = ""; };
  pano.addEventListener("pointerup", endDrag);
  pano.addEventListener("pointercancel", endDrag);
  pano.addEventListener("wheel", (ev) => { ev.preventDefault(); panorama.zoom(ev.deltaY > 0 ? 1.15 : 1 / 1.15); requestDraw(); }, { passive: false });
  pano.addEventListener("keydown", (ev) => {
    const keys = { ArrowLeft: [-5, 0], ArrowRight: [5, 0], ArrowUp: [0, 3], ArrowDown: [0, -3] };
    if (keys[ev.key]) { ev.preventDefault(); panorama.pan(...keys[ev.key]); requestDraw(); }
    else if (ev.key === "+" || ev.key === "=") { panorama.zoom(1 / 1.2); requestDraw(); }
    else if (ev.key === "-") { panorama.zoom(1.2); requestDraw(); }
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
    else render(); // повертаємо тіні
  });
  new ResizeObserver(() => { if (mode !== "3d") requestDraw(); }).observe(pano);
  new IntersectionObserver(([e]) => {
    visible = e.isIntersecting;
    ensure3D();
    view3d?.setRunning(mode === "3d" && visible);
    if (visible) requestDraw();
  }).observe(root);

  exagOut.textContent = exagInput.value;
  onLangChange(() => { render(); renderStatus(); requestDraw(); }); // canvas і складені речення перемальовуються
  setMode(mode);
  subscribe((st) => { clearTimeout(timer); timer = setTimeout(() => load(st), 300); });
}
