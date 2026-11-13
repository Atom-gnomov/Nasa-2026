// Модуль «Глобус Місяця» (М12, задачі G1/G2/G5): рельєф LOLA, кольорова карта LROC, координатна сітка,
// розгортання кулі у 2D (циліндрична карта, полярна стереографічна проєкція), освітлення Сонцем на дату.
//
// Дані (готує tools/build_globe_textures.py, усе — офіційні продукти NASA):
//   • куля: сітка вершин 0,25° і нахили з LOLA LDEM_16 (PDS), колір — CGI Moon Kit (SVS 4720);
//   • південний полюс: окремі детальні ділянки з LOLA LDEM_80S_80M і LDEM_875S_20M (PDS) у їхній рідній
//     полярній стереографічній проєкції (dsmap_polar.cat) + маски горизонту для тіней від рельєфу;
//   • Сонце: підсонячна точка з /api/system (JPL DE440, орієнтація Місяця IAU 2015);
//   • висота під курсором: /api/elevation (найдетальніший DEM LOLA, білінійно).
// Позиція вершини — зважена сума трьох видів (куля, карта, полюс), тому перемикання — плавна анімація.
import * as THREE from "three";
import { createScene } from "./three/scene.js";
import { getState, setState, subscribe } from "./state.js";

const ASSETS = "/assets/globe/";
const DEG = Math.PI / 180;
const R_M = 1737400;
const POLAR_EDGE_LAT = -45; // межа полярного виду
const SUN_RADIUS_DEG = 0.267;
const GRID_STEPS = [45, 30, 15, 10, 5, 2, 1, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01];
const LON_MULTS = [1, 2, 3, 6, 9, 18, 36, 90, 180, 360, 900, 1800, 3600];
const VIEWS = {
  globe: { w: [1, 0, 0] },
  map: { w: [0, 1, 0], camera: [0, 0, 7.2] },
  polar: { w: [0, 0, 1], camera: [0, 0, 2.3] },
};

const $ = (id) => document.getElementById(id);
const host = $("moon-globe");

// ---------- Формули видів (мають збігатися з шейдерами) ----------
function polarRadius(latDeg) {
  return 2 * Math.tan(Math.PI / 4 + Math.min(latDeg, POLAR_EDGE_LAT) * DEG / 2);
}

function viewPosition(w, latDeg, lonDeg, lift = 0) {
  const la = latDeg * DEG, lo = lonDeg * DEG, r = polarRadius(latDeg);
  const s = 1 + lift;
  return new THREE.Vector3(
    w[0] * Math.cos(la) * Math.sin(lo) * s + w[1] * lo + w[2] * r * Math.sin(lo),
    w[0] * Math.sin(la) * s + w[1] * la + w[2] * r * Math.cos(lo),
    w[0] * Math.cos(la) * Math.cos(lo) * s + (w[1] + w[2]) * lift,
  );
}

const unitUp = (latDeg, lonDeg) => viewPosition([1, 0, 0], latDeg, lonDeg);

function lonMultiplier(latDeg) {
  const need = 0.6 / Math.max(Math.cos(latDeg * DEG), 1e-5);
  return LON_MULTS.find((m) => m >= need) ?? LON_MULTS.at(-1);
}

function fmtLat(v, dec) {
  if (Math.abs(v) < 1e-9) return "0°";
  return `${Math.abs(v).toFixed(dec)}° ${v > 0 ? "пн." : "пд."}`;
}

function fmtLon(v, dec) {
  const x = ((v + 540) % 360) - 180;
  if (Math.abs(x) < 1e-9 || Math.abs(Math.abs(x) - 180) < 1e-9) return `${Math.abs(x).toFixed(dec)}°`;
  return `${Math.abs(x).toFixed(dec)}° ${x > 0 ? "сх." : "зх."}`;
}

const decimalsFor = (step) => Math.max(0, Math.ceil(-Math.log10(step) - 1e-9));
const fmtDist = (m) => (m >= 1000 ? `${+(m / 1000).toFixed(m >= 10000 ? 0 : 1)} км` : `${Math.round(m)} м`);

// ---------- Шейдери ----------
const commonFragment = /* glsl */ `
  uniform float uExag;
  uniform vec3 uLight;
  uniform vec3 uSunDir;
  uniform float uSunMode;
  uniform float uGridOn;
  uniform float uGridStep;
  uniform vec3 uGridColor;
  varying vec3 vUp;
  varying vec3 vEast;
  varying vec3 vNorth;
  const float SUN_R = ${SUN_RADIUS_DEG.toFixed(3)};
  const float MULTS[13] = float[13](${LON_MULTS.map((m) => m.toFixed(1)).join(", ")});

  float lonMult(float lat) {
    float need = 0.6 / max(cos(radians(lat)), 1e-5);
    for (int i = 0; i < 13; i++) { if (MULTS[i] >= need) return MULTS[i]; }
    return MULTS[12];
  }

  float gridLine(float v, float step, float width) {
    float d = abs(fract(v / step + 0.5) - 0.5) * step;
    float fw = max(fwidth(v), 1e-7);
    return 1.0 - smoothstep(0.5 * width * fw, (0.5 * width + 1.0) * fw, d);
  }

  // Локальний базис кулі (не залежить від виду): угору, схід, північ
  void globeFrame(vec2 ll, out vec3 up, out vec3 e, out vec3 n) {
    float lo = radians(ll.x), la = radians(ll.y);
    up = vec3(cos(la) * sin(lo), sin(la), cos(la) * cos(lo));
    e = vec3(cos(lo), 0.0, -sin(lo));
    n = vec3(-sin(la) * sin(lo), cos(la), -sin(la) * cos(lo));
  }

  // Кут Сонця над математичним горизонтом точки, градуси, і азимут від півночі за годинниковою
  vec2 sunElAz(vec2 ll) {
    vec3 up, e, n;
    globeFrame(ll, up, e, n);
    return vec2(degrees(asin(clamp(dot(up, uSunDir), -1.0, 1.0))), mod(degrees(atan(dot(e, uSunDir), dot(n, uSunDir))) + 360.0, 360.0));
  }

  // s — нахили (схід, північ); sunVisible — частка диска Сонця над горизонтом рельєфу (0…1)
  vec3 lighting(vec3 base, vec2 s, vec2 ll, float sunVisible) {
    if (uSunMode > 0.5) {
      vec3 up, e, n;
      globeFrame(ll, up, e, n);
      vec3 nn = normalize(up - uExag * (s.x * e + s.y * n));
      float lit = max(dot(nn, uSunDir), 0.0) * sunVisible;
      // яскравість ~ √(cos i): нелінійно, щоб при низькому полярному Сонці було видно освітлені схили
      return base * (0.02 + 1.25 * sqrt(lit));
    }
    vec3 nn = normalize(vUp - uExag * (s.x * vEast + s.y * vNorth));
    return base * (0.18 + 1.05 * max(dot(nn, uLight), 0.0));
  }

  vec3 drawGrid(vec3 c, vec2 ll) {
    if (uGridOn < 0.5) return c;
    float lat = ll.y, lon = ll.x;
    float lonStep = uGridStep * lonMult(lat);
    float fadeLon = 1.0 - smoothstep(0.15 * lonStep, 0.35 * lonStep, fwidth(lon));
    float g = max(gridLine(lat, uGridStep, 1.0), gridLine(lon, lonStep, 1.0) * fadeLon);
    float major = max(gridLine(lat, 90.0, 2.2) * (1.0 - step(89.0, abs(lat))),
                      gridLine(lon, 180.0, 2.2) * (1.0 - smoothstep(30.0, 60.0, fwidth(lon))));
    c = mix(c, uGridColor, 0.55 * g);
    return mix(c, vec3(1.0, 0.55, 0.2), 0.8 * major);
  }
`;

const viewFrames = /* glsl */ `
  uniform vec3 uW;
  uniform float uExag;
  varying vec3 vUp;
  varying vec3 vEast;
  varying vec3 vNorth;
  void setFrames(float lo, float la) {
    vec3 up = vec3(cos(la) * sin(lo), sin(la), cos(la) * cos(lo));
    vUp = normalize(uW.x * up + (uW.y + uW.z) * vec3(0.0, 0.0, 1.0));
    vEast = normalize(uW.x * vec3(cos(lo), 0.0, -sin(lo)) + uW.y * vec3(1.0, 0.0, 0.0)
                      + uW.z * vec3(cos(lo), -sin(lo), 0.0) + vec3(1e-6));
    vNorth = normalize(uW.x * vec3(-sin(la) * sin(lo), cos(la), -sin(la) * cos(lo)) + uW.y * vec3(0.0, 1.0, 0.0)
                       + uW.z * vec3(sin(lo), cos(lo), 0.0) + vec3(1e-6));
  }
`;

const globeVertex = /* glsl */ `
  attribute vec2 aLonLat;
  attribute float aHeight;  // висота / радіус Місяця
  varying vec2 vLonLat;
  ${viewFrames}
  const float EDGE = ${POLAR_EDGE_LAT.toFixed(1)};
  void main() {
    float lo = radians(aLonLat.x), la = radians(aLonLat.y);
    float h = aHeight * uExag;
    vec3 up = vec3(cos(la) * sin(lo), sin(la), cos(la) * cos(lo));
    float r = 2.0 * tan(0.7853981634 + radians(min(aLonLat.y, EDGE)) * 0.5);
    vec3 p = uW.x * up * (1.0 + h) + uW.y * vec3(lo, la, h) + uW.z * vec3(r * sin(lo), r * cos(lo), h);
    setFrames(lo, la);
    vLonLat = aLonLat;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
  }
`;

const globeFragment = /* glsl */ `
  uniform sampler2D uColor;
  uniform sampler2D uSlope;
  uniform float uSlopeScale;
  uniform vec3 uW;
  uniform float uTileEdge;  // південніше — малюють детальні полярні ділянки
  varying vec2 vLonLat;
  ${commonFragment}
  const float EDGE = ${POLAR_EDGE_LAT.toFixed(1)};
  void main() {
    if (uW.z > 0.35 && vLonLat.y > EDGE + 0.01) discard;
    if (vLonLat.y < uTileEdge) discard;
    vec2 uv = vec2((vLonLat.x + 180.0) / 360.0, (vLonLat.y + 90.0) / 180.0);
    vec3 base = texture2D(uColor, uv).rgb;
    vec2 s = (texture2D(uSlope, uv).rg * 255.0 - 128.0) / 127.0 * uSlopeScale;
    // Без маски рельєфу: диск Сонця над математичним горизонтом
    float vis = clamp((sunElAz(vLonLat).x + SUN_R) / (2.0 * SUN_R), 0.0, 1.0);
    vec3 c = lighting(base, s, vLonLat, vis);
    gl_FragColor = vec4(drawGrid(c, vLonLat), 1.0);
    #include <colorspace_fragment>
  }
`;

const tileVertex = /* glsl */ `
  attribute vec2 aXY;       // площина полярної проєкції, одиниці — радіус Місяця
  attribute float aHeight;  // висота / радіус Місяця
  varying vec2 vXY;
  ${viewFrames}
  void main() {
    float la = -1.5707963268 + 2.0 * atan(0.5 * length(aXY));
    float lo = atan(aXY.x, aXY.y);
    float h = aHeight * uExag;
    vec3 up = vec3(cos(la) * sin(lo), sin(la), cos(la) * cos(lo));
    vec3 p = uW.x * up * (1.0 + h) + uW.z * vec3(aXY, h);
    setFrames(lo, la);
    vXY = aXY;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
  }
`;

const tileFragment = /* glsl */ `
  uniform sampler2D uColor;
  uniform sampler2D uTileSlope;
  uniform sampler2D uHorizon;
  uniform float uSlopeScale;
  uniform float uHalf;     // половина сторони ділянки, одиниці — радіус Місяця
  uniform float uEdge;     // північна межа ділянки, градуси
  uniform float uInner;    // південніше — малює детальніша ділянка
  uniform float uAz;       // кількість азимутів у масці
  uniform float uBlocks;   // блоків в атласі
  uniform float uHSize;    // сторона маски, пікселі
  uniform vec2 uHRange;    // діапазон кодування кутів, градуси
  uniform float uColorLod;
  varying vec2 vXY;
  ${commonFragment}

  float horizonBin(vec2 uv, float i) {
    float b = floor(i / 3.0 + 1e-4);
    float c = i - 3.0 * b;
    float vLocal = clamp(uv.y, 0.5 / uHSize, 1.0 - 0.5 / uHSize);
    vec3 t = texture2D(uHorizon, vec2(uv.x, (vLocal + (uBlocks - 1.0 - b)) / uBlocks)).rgb;
    float v = c < 0.5 ? t.r : (c < 1.5 ? t.g : t.b);
    return mix(uHRange.x, uHRange.y, v);
  }

  float horizonAt(vec2 uv, float az) {
    float f = az / 360.0 * uAz;
    float i0 = mod(floor(f), uAz);
    return mix(horizonBin(uv, i0), horizonBin(uv, mod(i0 + 1.0, uAz)), fract(f));
  }

  void main() {
    // lat/lon рахуємо з лінійних координат площини — без розриву довготи на ±180°
    float r = length(vXY);
    vec2 ll = vec2(degrees(atan(vXY.x, vXY.y)), degrees(-1.5707963268 + 2.0 * atan(0.5 * r)));
    if (ll.y > uEdge || ll.y < uInner) discard;
    vec2 uv = 0.5 + vXY / (2.0 * uHalf);
    vec2 sxy = (texture2D(uTileSlope, uv).rg * 255.0 - 128.0) / 127.0 * uSlopeScale;
    float lo = radians(ll.x);
    vec2 s = vec2(sxy.x * cos(lo) - sxy.y * sin(lo), sxy.x * sin(lo) + sxy.y * cos(lo));
    // Кольорової зйомки тут немає (SVS 4720: LROC WAC лише до 70°), тому беремо згладжене альбедо
    vec3 base = textureLod(uColor, vec2((ll.x + 180.0) / 360.0, (ll.y + 90.0) / 180.0), uColorLod).rgb;
    float vis = 1.0;
    if (uSunMode > 0.5) {
      vec2 ea = sunElAz(ll);
      vis = clamp((ea.x - horizonAt(uv, ea.y) + SUN_R) / (2.0 * SUN_R), 0.0, 1.0);
    }
    vec3 c = lighting(base, s, ll, vis);
    gl_FragColor = vec4(drawGrid(c, ll), 1.0);
    #include <colorspace_fragment>
  }
`;

// ---------- Завантаження даних ----------
async function loadAssets() {
  const metaRes = await fetch(ASSETS + "globe.json", { cache: "no-cache" });
  if (!metaRes.ok) throw new Error("no-assets");
  const meta = await metaRes.json();
  const url = (file) => `${ASSETS}${file}?v=${meta.version ?? 0}`;
  const loader = new THREE.TextureLoader();
  const bin = (file) => fetch(url(file)).then((r) => r.arrayBuffer());
  const [heightBuf, color, slope] = await Promise.all([
    bin(meta.height.file), loader.loadAsync(url(meta.color.file)), loader.loadAsync(url(meta.slope.file)),
  ]);
  const tiles = await Promise.all((meta.polar_tiles ?? []).map(async (t) => {
    const [h, s, hz] = await Promise.all([
      bin(t.height.file), loader.loadAsync(url(t.slope.file)), loader.loadAsync(url(t.horizon.file)),
    ]);
    return { meta: t, heights: new Float32Array(h), slope: s, horizon: hz };
  }));
  return { meta, heights: new Int16Array(heightBuf), color, slope, tiles };
}

function buildGlobeGeometry({ meta, heights }) {
  const { lon_count: nLon, lat_count: nLat, step_deg: step } = meta.height;
  const count = nLon * nLat;
  const lonLat = new Float32Array(count * 2);
  const height = new Float32Array(count);
  const position = new Float32Array(count * 3);
  for (let i = 0; i < nLat; i++) {
    const lat = 90 - i * step;
    for (let j = 0; j < nLon; j++) {
      const k = i * nLon + j, lon = -180 + j * step;
      lonLat[2 * k] = lon;
      lonLat[2 * k + 1] = lat;
      height[k] = heights[k] / R_M;
      position.set(unitUp(lat, lon).toArray(), 3 * k);
    }
  }
  return gridGeometry(nLat, nLon, { position, aLonLat: [lonLat, 2], aHeight: [height, 1] });
}

function buildTileGeometry(tile) {
  const v = tile.meta.height.segments;
  const n = v + 1;
  const half = tile.meta.half_extent_m / R_M;
  const xy = new Float32Array(n * n * 2);
  const height = new Float32Array(n * n);
  const position = new Float32Array(n * n * 3);
  for (let i = 0; i < n; i++) {
    // рядок 0 у файлі — низ (−y); у сітці геометрії рядок 0 — верх, тому i → n−1−i
    const y = half - (2 * half * i) / v;
    for (let j = 0; j < n; j++) {
      const k = i * n + j, x = -half + (2 * half * j) / v;
      xy[2 * k] = x;
      xy[2 * k + 1] = y;
      height[k] = tile.heights[(n - 1 - i) * n + j] / R_M;
      position.set([x, y, 0], 3 * k);
    }
  }
  return gridGeometry(n, n, { position, aXY: [xy, 2], aHeight: [height, 1] });
}

function gridGeometry(rows, cols, attrs) {
  const index = new Uint32Array((rows - 1) * (cols - 1) * 6);
  let p = 0;
  for (let i = 0; i < rows - 1; i++) {
    for (let j = 0; j < cols - 1; j++) {
      const a = i * cols + j, b = a + 1, c = a + cols, d = c + 1;
      index.set([a, c, b, b, c, d], p);
      p += 6;
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(attrs.position, 3));
  for (const [name, val] of Object.entries(attrs)) {
    if (name !== "position") geo.setAttribute(name, new THREE.BufferAttribute(val[0], val[1]));
  }
  geo.setIndex(new THREE.BufferAttribute(index, 1));
  geo.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 4);
  return geo;
}

function heightAtM({ meta, heights }, lat, lon) {
  const { lon_count: nLon, lat_count: nLat, step_deg: step } = meta.height;
  const i = Math.min(nLat - 1, Math.max(0, Math.round((90 - lat) / step)));
  const j = Math.min(nLon - 1, Math.max(0, Math.round((((lon + 540) % 360) - 180 + 180) / step)));
  return heights[i * nLon + j];
}

function dotTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 32;
  const g = c.getContext("2d");
  g.beginPath(); g.arc(16, 16, 12, 0, 2 * Math.PI);
  g.fillStyle = "#fff"; g.fill();
  g.lineWidth = 4; g.strokeStyle = "#000"; g.stroke();
  return new THREE.CanvasTexture(c);
}

// ---------- Панель джерел ----------
function renderSources(meta) {
  const list = $("globe-sources-list");
  if (!list) return;
  const items = [
    [`Колір: CGI Moon Kit 2025 (${meta.color.width}×${meta.color.height}) — LROC WAC між 70° пн. і 70° пд., ближче до полюсів — альбедо LOLA; NASA позначає карту як візуалізаційну, не наукову`, meta.color.url],
    [`Рельєф кулі: LOLA ${meta.relief_source.id.toUpperCase()} ${meta.relief_source.product_version}, ${(meta.relief_source.resolution_m / 1000).toFixed(1)} км/піксель (PDS)`, meta.relief_source.url],
    ...(meta.polar_tiles ?? []).map((t) => [
      `Південний полюс: LOLA ${t.id.toUpperCase()} ${t.product_version}, ${t.resolution_m} м/піксель, до ${Math.abs(t.edge_lat)}° пд.; тіні — маски горизонту ${t.horizon.azimuths} азимутів до ${t.horizon.max_distance_km} км`,
      t.url,
    ]),
    ["Висота під курсором: найдетальніший DEM LOLA з PDS (20 м / 80 м / 474 м / 1,9 км), білінійно", "https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/"],
    ["Сонце: JPL DE440 (skyfield), орієнтація Місяця IAU 2015 (Archinal et al. 2018), система MEAN EARTH/POLAR AXIS", "https://ssd.jpl.nasa.gov/planets/eph_export.html"],
    ["Проєкції: LOLA dsmap.cat / dsmap_polar.cat (полярна: 0° угорі, 90° сх. праворуч)", "https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/catalog/"],
    ["Місця посадки: NSSDC (Apollo, Wagner et al. 2017), LROC (Chang'e 4, Chandrayaan-3), газетир IAU/USGS (Шеклтон)", "https://nssdc.gsfc.nasa.gov/planetary/lunar/lunar_sites.html"],
  ];
  list.replaceChildren(...items.map(([text, href]) => {
    const li = document.createElement("li");
    li.append(text + " — ");
    const a = document.createElement("a");
    a.href = href; a.target = "_blank"; a.rel = "noopener"; a.textContent = "джерело";
    li.append(a);
    return li;
  }));
}

// ---------- Основна функція ----------
async function main() {
  let data;
  try {
    data = await loadAssets();
  } catch {
    host.innerHTML = '<p class="placeholder">Немає даних глобуса. Запустіть <code>python tools/build_globe_textures.py</code></p>';
    return;
  }
  const ctx = createScene(host);
  if (!ctx) return;
  const { scene, camera, renderer, controls } = ctx;
  camera.near = 0.00005;
  camera.far = 100;
  camera.updateProjectionMatrix();
  renderSources(data.meta);

  const maxAniso = renderer.capabilities.getMaxAnisotropy();
  data.color.colorSpace = THREE.SRGBColorSpace;
  for (const t of [data.color, data.slope]) {
    t.wrapS = THREE.RepeatWrapping;
    t.anisotropy = maxAniso;
  }

  // Спільні uniform-и (один об'єкт value на всі матеріали)
  const shared = {
    uExag: { value: 1 },
    uLight: { value: new THREE.Vector3(0, 0, 1) },
    uSunDir: { value: new THREE.Vector3(0, 0, 1) },
    uSunMode: { value: 1 },
    uW: { value: new THREE.Vector3(1, 0, 0) },
    uGridOn: { value: 1 },
    uGridStep: { value: 10 },
    uGridColor: { value: new THREE.Color(0xf5b942) },
    uColor: { value: data.color },
    uSlopeScale: { value: data.meta.slope.slope_scale },
  };
  const tileEdge = { value: -90 };
  const globe = new THREE.Mesh(buildGlobeGeometry(data), new THREE.ShaderMaterial({
    uniforms: { ...shared, uSlope: { value: data.slope }, uTileEdge: tileEdge },
    vertexShader: globeVertex, fragmentShader: globeFragment,
  }));
  globe.frustumCulled = false;
  scene.add(globe);

  // Детальні полярні ділянки: від грубішої до детальнішої; кожна «вирізає» місце для наступної
  const tiles = data.tiles.sort((a, b) => b.meta.resolution_m - a.meta.resolution_m);
  const tileMeshes = tiles.map((t, i) => {
    t.slope.anisotropy = maxAniso;
    const inner = tiles[i + 1] ? tiles[i + 1].meta.edge_lat : -91;
    const m = new THREE.Mesh(buildTileGeometry(t), new THREE.ShaderMaterial({
      uniforms: {
        ...shared,
        uTileSlope: { value: t.slope },
        uHorizon: { value: t.horizon },
        uHalf: { value: t.meta.half_extent_m / R_M },
        uEdge: { value: t.meta.edge_lat },
        uInner: { value: inner },
        uAz: { value: t.meta.horizon.azimuths },
        uBlocks: { value: t.meta.horizon.blocks },
        uHSize: { value: t.meta.horizon.size },
        uHRange: { value: new THREE.Vector2(...t.meta.horizon.range_deg) },
        uColorLod: { value: 5 },
      },
      vertexShader: tileVertex, fragmentShader: tileFragment,
    }));
    m.frustumCulled = false;
    m.renderOrder = 1;
    scene.add(m);
    return m;
  });
  const coarsestTileEdge = tiles.length ? tiles[0].meta.edge_lat : -90;

  // Маркери: місця з каталогу та вибрана точка (без перевірки глибини — видимість рахуємо самі)
  const dot = dotTexture();
  const makePoints = (size, color) => {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(3), 3));
    const pts = new THREE.Points(geo, new THREE.PointsMaterial({
      size, color, map: dot, transparent: true, alphaTest: 0.3, sizeAttenuation: false, depthTest: false,
    }));
    pts.frustumCulled = false;
    pts.renderOrder = 3;
    scene.add(pts);
    return pts;
  };
  const sitePoints = makePoints(9, 0xdfe6ff);
  const selectedPoint = makePoints(15, 0xf5b942);
  let sites = [];
  fetch("/api/sites").then((r) => r.json()).then((list) => { sites = list; }).catch(() => {});

  // Шар підписів сітки
  const labelLayer = document.createElement("div");
  labelLayer.style.cssText = "position:absolute;inset:0;pointer-events:none;overflow:hidden";
  host.append(labelLayer);
  const labelPool = [];
  const getLabel = (i) => {
    while (labelPool.length <= i) {
      const el = document.createElement("div");
      el.className = "grid-label";
      el.style.position = "absolute";
      labelLayer.append(el);
      labelPool.push(el);
    }
    return labelPool[i];
  };

  // Лінійка масштабу
  const scaleEl = document.createElement("div");
  scaleEl.className = "scale-bar";
  scaleEl.innerHTML = "<span></span><i></i>";
  host.append(scaleEl);

  // ---------- Керування ----------
  let view = "globe";
  let anim = null;
  const w = [1, 0, 0];
  const gridToggle = $("grid-toggle");
  const gridStepSel = $("grid-step");
  const relief = $("relief");
  const reliefOut = $("relief-value");
  const lightSel = $("light-mode");
  const sunInfo = $("globe-sun");
  const warnEl = $("globe-warn");

  function configureControls(v) {
    const flat = v !== "globe";
    controls.enableRotate = !flat;
    controls.enablePan = flat;
    controls.zoomToCursor = flat;
    controls.screenSpacePanning = true;
    controls.mouseButtons = flat
      ? { LEFT: THREE.MOUSE.PAN, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN }
      : { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.ROTATE };
    controls.minDistance = flat ? 0.0002 : 1.0003;
    controls.maxDistance = flat ? 14 : 12;
  }

  const globeCameraFor = (lat, lon, dist) => unitUp(lat, lon).multiplyScalar(dist);

  function setView(next) {
    if (next === view && !anim) return;
    const camTo = next === "globe" ? globeCameraFor(-40, 0, 3.0) : new THREE.Vector3(...VIEWS[next].camera);
    anim = {
      from: [...w], to: VIEWS[next].w, camFrom: camera.position.clone(), camTo,
      tgtFrom: controls.target.clone(), t0: performance.now(), dur: 1100,
    };
    view = next;
    controls.enabled = false;
    for (const b of document.querySelectorAll("[data-view]")) b.classList.toggle("active", b.dataset.view === next);
  }

  function updateWarn() {
    const exag = Number(relief.value);
    warnEl.textContent = exag !== 1
      ? `Рельєф перебільшено ×${exag}: висоти й освітлення схилів не відповідають реальним (для точних показників — ×1).`
      : "";
  }

  for (const b of document.querySelectorAll("[data-view]")) b.addEventListener("click", () => setView(b.dataset.view));
  gridToggle.addEventListener("change", () => { shared.uGridOn.value = gridToggle.checked ? 1 : 0; });
  relief.addEventListener("input", () => {
    shared.uExag.value = Number(relief.value);
    reliefOut.textContent = relief.value;
    updateWarn();
  });
  lightSel.addEventListener("change", () => { shared.uSunMode.value = lightSel.value === "sun" ? 1 : 0; });

  camera.position.copy(globeCameraFor(-40, 0, 3.0));
  configureControls("globe");

  // ---------- Сонце на дату (JPL DE440) ----------
  let lastDatetime = null;
  let sysAbort = null;
  async function updateSun(datetime) {
    if (datetime === lastDatetime) return;
    lastDatetime = datetime;
    sysAbort?.abort();
    sysAbort = new AbortController();
    try {
      const res = await fetch(`/api/system?${new URLSearchParams({ datetime })}`, { signal: sysAbort.signal });
      const s = await res.json();
      if (!res.ok) throw new Error(s.detail);
      const p = s.sub_solar_point;
      shared.uSunDir.value.copy(unitUp(p.lat, p.lon));
      sunInfo.textContent = `Сонце в зеніті над ${fmtLat(p.lat, 2)}, ${fmtLon(p.lon, 2)} (${s.datetime})`;
    } catch (err) {
      if (err.name !== "AbortError") sunInfo.textContent = "Сонце: немає даних ефемерид";
    }
  }
  subscribe((st) => updateSun(st.datetime));

  // ---------- Вибір точки й висота під курсором ----------
  const raycaster = new THREE.Raycaster();
  const unitSphere = new THREE.Sphere(new THREE.Vector3(), 1);
  const plane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);

  function pick(ndcX, ndcY) {
    if (anim) return null;
    raycaster.setFromCamera(new THREE.Vector2(ndcX, ndcY), camera);
    const p = new THREE.Vector3();
    if (view === "globe") {
      if (!raycaster.ray.intersectSphere(unitSphere, p)) return null;
      return { lat: Math.asin(THREE.MathUtils.clamp(p.y, -1, 1)) / DEG, lon: Math.atan2(p.x, p.z) / DEG };
    }
    if (!raycaster.ray.intersectPlane(plane, p)) return null;
    if (view === "map") {
      const lat = p.y / DEG, lon = p.x / DEG;
      return Math.abs(lat) <= 90 && Math.abs(lon) <= 180 ? { lat, lon } : null;
    }
    const r = Math.hypot(p.x, p.y);
    const lat = (2 * Math.atan(r / 2) - Math.PI / 2) / DEG;
    return lat <= POLAR_EDGE_LAT ? { lat, lon: Math.atan2(p.x, p.y) / DEG } : null;
  }

  function eventNdc(ev) {
    const rect = renderer.domElement.getBoundingClientRect();
    return [((ev.clientX - rect.left) / rect.width) * 2 - 1, -((ev.clientY - rect.top) / rect.height) * 2 + 1];
  }

  const cursorEl = $("globe-cursor");
  let elevTimer = null;
  let elevAbort = null;
  renderer.domElement.addEventListener("pointermove", (ev) => {
    const hit = pick(...eventNdc(ev));
    clearTimeout(elevTimer);
    if (!hit) { cursorEl.textContent = "Курсор: —"; return; }
    const where = `${fmtLat(hit.lat, 4)}, ${fmtLon(hit.lon, 4)}`;
    cursorEl.textContent = `Курсор: ${where} · висота …`;
    elevTimer = setTimeout(async () => {
      elevAbort?.abort();
      elevAbort = new AbortController();
      try {
        const q = new URLSearchParams({ lat: hit.lat.toFixed(5), lon: hit.lon.toFixed(5) });
        const res = await fetch(`/api/elevation?${q}`, { signal: elevAbort.signal });
        const e = await res.json();
        cursorEl.textContent = res.ok
          ? `Курсор: ${where} · висота ${e.height_m.toFixed(0)} м (LOLA ${e.source.id.toUpperCase()}, ${fmtDist(e.source.resolution_m)}/пікс.)`
          : `Курсор: ${where} · висота: ${e.detail}`;
      } catch (err) {
        if (err.name !== "AbortError") cursorEl.textContent = `Курсор: ${where}`;
      }
    }, 120);
  });

  let downAt = null;
  renderer.domElement.addEventListener("pointerdown", (ev) => { downAt = [ev.clientX, ev.clientY]; });
  renderer.domElement.addEventListener("pointerup", (ev) => {
    if (!downAt || Math.hypot(ev.clientX - downAt[0], ev.clientY - downAt[1]) > 4) return;
    const hit = pick(...eventNdc(ev));
    if (hit) setState({ site: null, lat: Number(hit.lat.toFixed(5)), lon: Number(hit.lon.toFixed(5)) });
  });

  // ---------- Кадр ----------
  const lightLocal = new THREE.Vector3(-0.45, 0.55, 0.7).normalize();

  function worldPerPx() {
    const dist = view === "globe" ? camera.position.distanceTo(controls.target) - 1 : camera.position.z;
    return (2 * Math.max(dist, 1e-6) * Math.tan((camera.fov * DEG) / 2)) / Math.max(host.clientHeight, 1);
  }

  function autoGridStep() {
    const want = (worldPerPx() / DEG) * 45; // ~45 пікселів між лініями
    return [...GRID_STEPS].reverse().find((s) => s >= want) ?? GRID_STEPS[0];
  }

  function updateScaleBar(center) {
    // метрів на піксель у центрі кадру (у полярній проєкції — з поправкою на масштаб k)
    let mpp = worldPerPx() * R_M;
    if (view === "polar" && center) mpp /= 2 / (1 + Math.sin(Math.abs(center.lat) * DEG));
    if (!center || anim) { scaleEl.style.display = "none"; return; }
    const target = mpp * 110;
    const pow = 10 ** Math.floor(Math.log10(target));
    const nice = [5, 2, 1].map((m) => m * pow).find((v) => v <= target) ?? pow;
    scaleEl.style.display = "";
    scaleEl.querySelector("i").style.width = `${nice / mpp}px`;
    scaleEl.querySelector("span").textContent = fmtDist(nice) + (view === "map" ? " (пн.–пд.)" : "");
  }

  function facingCamera(p) {
    return w[0] < 0.5 || p.clone().normalize().dot(camera.position.clone().sub(p).normalize()) > 0.02;
  }

  function updateMarkers() {
    const exag = shared.uExag.value;
    const liftFor = (lat, lon) => (heightAtM(data, lat, lon) / R_M) * exag;
    const pts = [];
    for (const s of sites) {
      if (w[2] >= 0.35 && s.lat > POLAR_EDGE_LAT) continue;
      const p = viewPosition(w, s.lat, s.lon, liftFor(s.lat, s.lon));
      if (facingCamera(p)) pts.push(...p.toArray());
    }
    sitePoints.geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(pts.length ? pts : [0, 0, 0]), 3));
    sitePoints.geometry.setDrawRange(0, pts.length / 3);

    const { lat, lon } = getState();
    let show = lat !== null && lon !== null && (w[2] < 0.35 || lat <= POLAR_EDGE_LAT);
    if (show) {
      const p = viewPosition(w, lat, lon, liftFor(lat, lon));
      show = facingCamera(p);
      selectedPoint.geometry.attributes.position.array.set(p.toArray());
      selectedPoint.geometry.attributes.position.needsUpdate = true;
    }
    selectedPoint.visible = show;
  }

  function updateLabels(step, center) {
    let used = 0;
    if (shared.uGridOn.value > 0.5 && center) {
      const dec = decimalsFor(step);
      const rect = { w: host.clientWidth, h: host.clientHeight };
      const place = (lat, lon, text) => {
        const p = viewPosition(w, lat, lon);
        if (view === "globe" && p.clone().normalize().dot(camera.position.clone().sub(p).normalize()) < 0.35) return;
        const s = p.project(camera);
        if (s.z > 1 || Math.abs(s.x) > 1.02 || Math.abs(s.y) > 1.02) return;
        const el = getLabel(used++);
        el.textContent = text;
        el.style.display = "";
        el.style.transform = `translate(${((s.x + 1) / 2) * rect.w + 3}px, ${((1 - s.y) / 2) * rect.h - 14}px)`;
      };
      const lat0 = Math.round(center.lat / step) * step;
      for (let k = -12; k <= 12; k++) {
        const lat = lat0 + k * step;
        if (lat <= -90 || lat >= 90 || (view === "polar" && lat > POLAR_EDGE_LAT)) continue;
        place(lat, center.lon, fmtLat(lat, dec));
      }
      let labelLat = THREE.MathUtils.clamp(center.lat, -85, 85);
      if (view === "polar") {
        const ring = polarRadius(center.lat) + 0.35 * camera.position.z * Math.tan((camera.fov * DEG) / 2);
        labelLat = Math.min((2 * Math.atan(ring / 2) - Math.PI / 2) / DEG, POLAR_EDGE_LAT);
      }
      const lonStep = step * lonMultiplier(labelLat);
      const lon0 = Math.round(center.lon / lonStep) * lonStep;
      const span = view === "polar" ? Math.ceil(180 / lonStep) : 12;
      for (let k = -span; k <= span && k * lonStep < 360; k++) {
        const lon = lon0 + k * lonStep;
        if (view !== "polar" && Math.abs(lon) > 180) continue;
        place(labelLat, lon, fmtLon(lon, decimalsFor(lonStep)));
      }
    }
    for (let i = used; i < labelPool.length; i++) labelPool[i].style.display = "none";
  }

  renderer.setAnimationLoop((now) => {
    if (anim) {
      const t = Math.min(1, (now - anim.t0) / anim.dur);
      const e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      for (let i = 0; i < 3; i++) w[i] = anim.from[i] + (anim.to[i] - anim.from[i]) * e;
      camera.position.lerpVectors(anim.camFrom, anim.camTo, e);
      controls.target.lerpVectors(anim.tgtFrom, new THREE.Vector3(), e);
      camera.lookAt(controls.target);
      if (t >= 1) {
        anim = null;
        configureControls(view);
        controls.enabled = true;
      }
    }
    shared.uW.value.set(...w);
    // Полярні ділянки не мають циліндричної форми — на карті (і під час переходу до неї) їх ховаємо
    const tilesOn = w[1] < 1e-4 && tileMeshes.length > 0;
    for (const m of tileMeshes) m.visible = tilesOn;
    tileEdge.value = tilesOn ? coarsestTileEdge : -91;

    if (!anim && view !== "globe") {
      camera.position.x = controls.target.x;
      camera.position.y = controls.target.y;
    }
    if (!anim && view === "globe") {
      const d = camera.position.distanceTo(controls.target) - 1;
      controls.rotateSpeed = THREE.MathUtils.clamp(d / 2, 0.002, 1);
    }
    controls.update();

    const center = pick(0, 0);
    const step = gridStepSel.value === "auto" ? autoGridStep() : Number(gridStepSel.value);
    shared.uGridStep.value = step;
    $("globe-grid-label").textContent = shared.uGridOn.value > 0.5 ? `Сітка: ${step}°` : "";
    shared.uLight.value.copy(lightLocal).applyQuaternion(camera.quaternion);

    updateMarkers();
    updateLabels(step, center);
    updateScaleBar(center);
    renderer.render(scene, camera);
  });
}

main();
