// Модуль «3D-вид системи» (М13, задачі G3, G8): Сонце, Земля, Місяць на реальних положеннях з /api/system.
//
// Рамка сцени — екліптика J2000: орбіта Землі горизонтальна, вісь Землі нахилена на 23,44°.
// ICRF (x, y, z) → екліптика → Three.js (x, z, −y), як у docs/CONTRACTS.md §5.4 (Y угору).
// Тіла повертаються матрицями з бекенду: moon_orientation (ICRF → MOON_ME), earth_orientation (ICRF → ITRS).
// Кожне тіло освітлюється справжнім напрямком на Сонце (а не з намальованої позиції), тому фаза Місяця
// й межа дня і ночі точні і в схематичному масштабі, де відстані стиснуто.
// Одиниця сцени — 1000 км.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { createScene } from "./three/scene.js";
import { getState, setState, subscribe } from "./state.js";

const DEG = Math.PI / 180;
const EPS = 23.4392911 * DEG; // нахил екліптики J2000 (IAU)
const R_EARTH = 6.378137; // тис. км (WGS84, екваторіальний)
const R_MOON = 1.7374; // тис. км (LOLA)
const R_SUN = 695.7; // тис. км (IAU 2015, номінальний)
const C_KM_S = 299792.458;
const EARTH_ROT_DEG_PER_DAY = 360.98564736629; // швидкість зоряного часу

const $ = (id) => document.getElementById(id);
const host = $("system-view");

// ICRF → сцена: рядки M = T · E (E — ICRF → екліптика, T — (x, y, z) → (x, z, −y))
const M_ICRF = [
  [1, 0, 0],
  [0, -Math.sin(EPS), Math.cos(EPS)],
  [0, -Math.cos(EPS), -Math.sin(EPS)],
];
const mul3 = (a, b) => a.map((row) => [0, 1, 2].map((j) => row[0] * b[0][j] + row[1] * b[1][j] + row[2] * b[2][j]));
const transpose = (m) => [0, 1, 2].map((i) => [m[0][i], m[1][i], m[2][i]]);
const apply3 = (m, v) => m.map((row) => row[0] * v[0] + row[1] * v[1] + row[2] * v[2]);
const toScene = (vKm) => new THREE.Vector3(...apply3(M_ICRF, vKm)).multiplyScalar(1 / 1000);
const dirScene = (vKm) => new THREE.Vector3(...apply3(M_ICRF, vKm)).normalize();
const unitLatLon = (lat, lon) => [Math.cos(lat * DEG) * Math.cos(lon * DEG), Math.cos(lat * DEG) * Math.sin(lon * DEG), Math.sin(lat * DEG)];
const fmtLat = (v) => `${Math.abs(v).toFixed(2)}° ${v >= 0 ? "пн." : "пд."}`;
const fmtLon = (v) => `${Math.abs(v).toFixed(2)}° ${v >= 0 ? "сх." : "зх."}`;
const fmtKm = (km) => `${Math.round(km).toLocaleString("uk-UA")} км`;
const isoUtc = (ms) => new Date(ms).toISOString().slice(0, 19) + "Z";

/** Тіло → сцена: матриця 4×4 з поворотом (тіло → ICRF → сцена), масштабом і позицією. */
function bodyMatrix(icrfToBody, radius, position) {
  const r = mul3(M_ICRF, transpose(icrfToBody));
  const m = new THREE.Matrix4().set(
    r[0][0] * radius, r[0][1] * radius, r[0][2] * radius, position.x,
    r[1][0] * radius, r[1][1] * radius, r[1][2] * radius, position.y,
    r[2][0] * radius, r[2][1] * radius, r[2][2] * radius, position.z,
    0, 0, 0, 1,
  );
  return { m, r };
}

/** Повертає ITRS на кут Δθ навколо осі Землі (екстраполяція обертання між запитами під час анімації). */
function rotateEarth(icrfToItrs, deltaDeg) {
  const a = deltaDeg * DEG;
  const rz = [[Math.cos(a), Math.sin(a), 0], [-Math.sin(a), Math.cos(a), 0], [0, 0, 1]];
  return mul3(rz, icrfToItrs);
}

// ---------- Геометрія й матеріали ----------
/** Куля в системі тіла (x — до довготи 0°, z — до півн. полюса), uv як у рівнопроміжній карті −180…180. */
function bodyGeometry(segLon = 192, segLat = 96) {
  const pos = [], uv = [], idx = [];
  for (let i = 0; i <= segLat; i++) {
    const lat = 90 - (180 * i) / segLat;
    for (let j = 0; j <= segLon; j++) {
      const lon = -180 + (360 * j) / segLon;
      pos.push(...unitLatLon(lat, lon));
      uv.push(j / segLon, 1 - i / segLat);
    }
  }
  for (let i = 0; i < segLat; i++) {
    for (let j = 0; j < segLon; j++) {
      const a = i * (segLon + 1) + j, b = a + 1, c = a + segLon + 1, d = c + 1;
      idx.push(a, c, b, b, c, d);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("normal", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2));
  g.setIndex(idx);
  return g;
}

function litMaterial(texture, fallbackColor, ambient) {
  return new THREE.ShaderMaterial({
    uniforms: {
      uMap: { value: texture },
      uHasMap: { value: texture ? 1 : 0 },
      uColor: { value: new THREE.Color(fallbackColor) },
      uSunDir: { value: new THREE.Vector3(1, 0, 0) },
      uAmbient: { value: ambient },
    },
    vertexShader: /* glsl */ `
      #include <common>
      #include <logdepthbuf_pars_vertex>
      varying vec2 vUv;
      varying vec3 vN;
      void main() {
        vUv = uv;
        vN = normalize(mat3(modelMatrix) * normal);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        #include <logdepthbuf_vertex>
      }`,
    fragmentShader: /* glsl */ `
      #include <logdepthbuf_pars_fragment>
      uniform sampler2D uMap;
      uniform float uHasMap;
      uniform vec3 uColor;
      uniform vec3 uSunDir;
      uniform float uAmbient;
      varying vec2 vUv;
      varying vec3 vN;
      void main() {
        #include <logdepthbuf_fragment>
        vec3 base = uHasMap > 0.5 ? texture2D(uMap, vUv).rgb : uColor;
        float lit = max(dot(normalize(vN), uSunDir), 0.0);
        gl_FragColor = vec4(base * (uAmbient + 1.05 * lit), 1.0);
        #include <colorspace_fragment>
      }`,
  });
}

function glowTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d");
  const grad = g.createRadialGradient(64, 64, 8, 64, 64, 64);
  grad.addColorStop(0, "rgba(255,240,200,0.95)");
  grad.addColorStop(0.3, "rgba(255,200,120,0.35)");
  grad.addColorStop(1, "rgba(255,160,60,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(c);
}

// ---------- Розкладка тіл у сцені (режим × масштаб) ----------
// Напрямки завжди справжні. У схематичному масштабі тіла збільшено, а відстані стиснуто
// ПРОПОРЦІЙНО (множенням на сталу), тому форма орбіт — ексцентриситет, нахил — зберігається.
const AU_SCENE = 149597.8707; // 1 а.о. у тис. км
const K_HELIO = (real) => (real ? 1 : 1000 / AU_SCENE); // 1 а.о. → 1000 одиниць
const K_MOON_HELIO = (real) => (real ? 1 : 90 / 384.4); // 384 400 км → 90 одиниць

function layout(mode, scale, s) {
  const moonRel = toScene(s.moon_km); // Місяць відносно Землі
  const sunRel = toScene(s.sun_km); // Сонце відносно Землі
  const real = scale === "real";
  if (mode === "earth-moon") {
    return {
      earth: { pos: new THREE.Vector3(), r: real ? R_EARTH : R_EARTH * 6 },
      moon: { pos: moonRel, r: real ? R_MOON : R_MOON * 6 },
      sun: { pos: real ? sunRel : sunRel.clone().setLength(3000), r: real ? R_SUN : 160 },
      overview: { target: new THREE.Vector3(), dist: 1100 },
    };
  }
  const earthPos = sunRel.clone().negate().multiplyScalar(K_HELIO(real));
  return {
    sun: { pos: new THREE.Vector3(), r: real ? R_SUN : 70 },
    earth: { pos: earthPos, r: real ? R_EARTH : 16 },
    moon: { pos: earthPos.clone().addScaledVector(moonRel, K_MOON_HELIO(real)), r: real ? R_MOON : 6 },
    overview: { target: new THREE.Vector3(), dist: real ? 420000 : 2900 },
  };
}

const lerpLayout = (a, b, e) => {
  const out = {};
  for (const k of ["sun", "earth", "moon"]) {
    out[k] = { pos: a[k].pos.clone().lerp(b[k].pos, e), r: a[k].r + (b[k].r - a[k].r) * e };
  }
  out.overview = { target: a.overview.target.clone().lerp(b.overview.target, e), dist: a.overview.dist + (b.overview.dist - a.overview.dist) * e };
  return out;
};

// ---------- Фаза Місяця ----------
function phaseName(fraction, waxing) {
  if (fraction < 0.03) return "молодик";
  if (fraction > 0.97) return "повня";
  if (Math.abs(fraction - 0.5) < 0.04) return waxing ? "перша чверть" : "остання чверть";
  if (fraction < 0.5) return waxing ? "молодий місяць (серп)" : "старий місяць (серп)";
  return waxing ? "зростаючий місяць" : "спадаючий місяць";
}

// ---------- Основна функція ----------
async function main() {
  let assets = null;
  try {
    const res = await fetch("/assets/system/system.json", { cache: "no-cache" });
    if (res.ok) assets = await res.json();
  } catch { /* немає даних — тіла будуть однотонними */ }

  const ctx = createScene(host, { logarithmicDepthBuffer: true });
  if (!ctx) return;
  const { scene, camera, renderer, controls } = ctx;
  camera.near = 0.001;
  camera.far = 5e6;
  camera.updateProjectionMatrix();
  controls.enableDamping = true;
  controls.zoomSpeed = 1.6;

  const loader = new THREE.TextureLoader();
  const loadTex = async (url) => {
    try {
      const t = await loader.loadAsync(url);
      t.colorSpace = THREE.SRGBColorSpace;
      t.anisotropy = renderer.capabilities.getMaxAnisotropy();
      return t;
    } catch { return null; }
  };
  const ver = assets?.version ?? 0;
  const [earthTex, moonTex] = await Promise.all([
    assets ? loadTex(`/assets/system/${assets.assets.earth.file}?v=${ver}`) : null,
    loadTex("/assets/globe/color.jpg"),
  ]);

  const geo = bodyGeometry();
  const earth = new THREE.Mesh(geo, litMaterial(earthTex, 0x3a6ea5, 0.05));
  const moon = new THREE.Mesh(geo, litMaterial(moonTex, 0x9a9a9a, 0.03));
  for (const m of [earth, moon]) { m.matrixAutoUpdate = false; scene.add(m); }

  // Сонце: модель NASA (glTF) або куля-заміна; поверх — м'яке сяйво
  const sun = new THREE.Group();
  scene.add(sun);
  let sunModelRadius = 1;
  if (assets) {
    try {
      const gltf = await new GLTFLoader().loadAsync(`/assets/system/${assets.assets.sun.file}?v=${ver}`);
      const box = new THREE.Box3().setFromObject(gltf.scene);
      const size = box.getSize(new THREE.Vector3());
      sunModelRadius = Math.max(size.x, size.y, size.z) / 2; // модель — куля: радіус = половина ребра коробки
      gltf.scene.position.sub(box.getCenter(new THREE.Vector3()));
      sun.add(gltf.scene);
    } catch { /* нижче — куля-заміна */ }
  }
  if (!sun.children.length) sun.add(new THREE.Mesh(new THREE.SphereGeometry(1, 48, 24), new THREE.MeshBasicMaterial({ color: 0xffcc66 })));
  const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture(), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true }));
  scene.add(glow);

  // Орбіти (/api/orbits): оскулюючі еліпси — замкнені лінії з 720 точок; справжній шлях — пунктир
  const orbitMat = (color) => new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.55 });
  const moonOrbit = new THREE.LineLoop(new THREE.BufferGeometry(), orbitMat(0xaab3c5));
  const earthOrbit = new THREE.LineLoop(new THREE.BufferGeometry(), orbitMat(0x5b8fd0));
  const pathMat = (color) => new THREE.LineDashedMaterial({ color, transparent: true, opacity: 0.9, dashSize: 1, gapSize: 1 });
  const moonPath = new THREE.Line(new THREE.BufferGeometry(), pathMat(0xf5b942));
  const earthPath = new THREE.Line(new THREE.BufferGeometry(), pathMat(0xf5b942));
  scene.add(moonOrbit, earthOrbit, moonPath, earthPath);
  let orbitData = null;

  // Вибрана точка на Місяці: маркер, площина горизонту, стрілки на Сонце й Землю
  const pointMarker = new THREE.Mesh(new THREE.SphereGeometry(1, 16, 8), new THREE.MeshBasicMaterial({ color: 0xf5b942 }));
  const horizonDisk = new THREE.Mesh(new THREE.CircleGeometry(1, 48),
    new THREE.MeshBasicMaterial({ color: 0xf5b942, transparent: true, opacity: 0.16, side: THREE.DoubleSide, depthWrite: false }));
  const toSunArrow = new THREE.ArrowHelper(new THREE.Vector3(1, 0, 0), new THREE.Vector3(), 1, 0xffd34d);
  const toEarthArrow = new THREE.ArrowHelper(new THREE.Vector3(1, 0, 0), new THREE.Vector3(), 1, 0x5aa9ff);
  scene.add(pointMarker, horizonDisk, toSunArrow, toEarthArrow);

  // Станції DSN і лінія зв'язку від точки до найкращої
  let stations = [];
  fetch("/api/dsn").then((r) => r.json()).then((list) => {
    stations = list.map((st) => ({
      ...st,
      mesh: (() => { const m = new THREE.Mesh(new THREE.SphereGeometry(1, 12, 6), new THREE.MeshBasicMaterial({ color: 0x8fd18f })); scene.add(m); return m; })(),
    }));
  }).catch(() => {});
  const linkLine = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]),
    new THREE.LineDashedMaterial({ color: 0x8fd18f, dashSize: 4, gapSize: 3 }));
  scene.add(linkLine);

  // Підписи
  const labelLayer = document.createElement("div");
  labelLayer.style.cssText = "position:absolute;inset:0;pointer-events:none;overflow:hidden";
  host.append(labelLayer);
  const makeLabel = (text, cls = "") => {
    const el = document.createElement("div");
    el.className = `body-label ${cls}`;
    el.textContent = text;
    labelLayer.append(el);
    return el;
  };
  const labels = { sun: makeLabel("Сонце"), earth: makeLabel("Земля"), moon: makeLabel("Місяць") };

  // ---------- Стан ----------
  let mode = host.dataset.mode;
  let scale = $("system-scale").value;
  let focus = "overview";
  let state = null; // останній SystemState
  let stateMs = 0;
  let simMs = Date.parse(getState().datetime) || Date.now();
  let playing = false;
  let fetching = false;
  let lastFetch = 0;
  let modeAnim = null; // {from, t0}
  let camAnim = null;
  let lastLayout = null;

  // ---------- Дані ----------
  async function fetchSystem(ms) {
    const res = await fetch(`/api/system?${new URLSearchParams({ datetime: isoUtc(ms) })}`);
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || "немає даних");
    return body;
  }

  async function loadState(ms) {
    fetching = true;
    lastFetch = performance.now();
    try {
      state = await fetchSystem(ms);
      stateMs = Date.parse(state.datetime);
      $("system-note").textContent = "";
    } catch (err) {
      $("system-note").textContent = `Немає даних ефемерид: ${err.message}`;
    } finally {
      fetching = false;
    }
  }

  // Орбіти — один запит; під час анімації оновлюються не частіше ніж раз на 0,5 с
  let orbitTimer = null;
  let orbitLoading = false;
  let orbitMs = NaN;
  function loadOrbits(ms, delay = 200) {
    clearTimeout(orbitTimer);
    orbitTimer = setTimeout(async () => {
      if (orbitLoading) return;
      orbitLoading = true;
      try {
        const res = await fetch(`/api/orbits?${new URLSearchParams({ datetime: isoUtc(ms) })}`);
        if (res.ok) { orbitData = await res.json(); orbitMs = ms; }
      } catch { /* лишаємо попередні */ } finally { orbitLoading = false; }
    }, delay);
  }

  // ---------- Керування ----------
  function setMode(next, push = true) {
    if (next === mode) return;
    modeAnim = { from: lastLayout, t0: performance.now() };
    mode = next;
    host.dataset.mode = next;
    for (const a of document.querySelectorAll("[data-mode]")) a.classList.toggle("active", a.dataset.mode === next);
    if (push) history.replaceState(null, "", `/system/${next}${location.search}`);
    setFocus(focus, true);
  }

  function setFocus(next, keepDirection = false) {
    focus = next;
    for (const b of document.querySelectorAll("[data-focus]")) b.classList.toggle("active", b.dataset.focus === next);
    camAnim = { t0: performance.now(), fromTarget: controls.target.clone(), fromOffset: camera.position.clone().sub(controls.target), keepDirection };
  }

  for (const a of document.querySelectorAll("[data-mode]")) {
    a.addEventListener("click", (ev) => { ev.preventDefault(); setMode(a.dataset.mode); });
  }
  for (const b of document.querySelectorAll("[data-focus]")) b.addEventListener("click", () => setFocus(b.dataset.focus));
  $("system-scale").addEventListener("change", (ev) => {
    modeAnim = { from: lastLayout, t0: performance.now() };
    scale = ev.target.value;
    setFocus(focus, true);
  });
  $("system-play").addEventListener("click", () => {
    playing = !playing;
    $("system-play").textContent = playing ? "⏸" : "▶";
    if (!playing) setState({ datetime: isoUtc(simMs).slice(0, 16) + "Z" }); // синхронізуємо календар і оверлей
  });
  $("system-now").addEventListener("click", () => {
    simMs = Date.now();
    setState({ datetime: isoUtc(simMs).slice(0, 16) + "Z" });
  });

  subscribe((st) => {
    if (playing) return;
    const ms = Date.parse(st.datetime);
    if (Number.isFinite(ms) && Math.abs(ms - stateMs) > 1000) {
      simMs = ms;
      loadState(ms);
      loadOrbits(ms);
    }
  });

  // Клік по Місяцю — вибір точки (спільний стан з вкладкою «Місяць»)
  const raycaster = new THREE.Raycaster();
  let downAt = null;
  renderer.domElement.addEventListener("pointerdown", (ev) => { downAt = [ev.clientX, ev.clientY]; });
  renderer.domElement.addEventListener("pointerup", (ev) => {
    if (!downAt || Math.hypot(ev.clientX - downAt[0], ev.clientY - downAt[1]) > 4) return;
    const rect = renderer.domElement.getBoundingClientRect();
    raycaster.setFromCamera(new THREE.Vector2(((ev.clientX - rect.left) / rect.width) * 2 - 1, -((ev.clientY - rect.top) / rect.height) * 2 + 1), camera);
    const hit = raycaster.intersectObject(moon)[0];
    if (!hit) return;
    const local = hit.point.clone().applyMatrix4(moon.matrixWorld.clone().invert()).normalize();
    setState({ site: null, lat: +(Math.asin(local.z) / DEG).toFixed(5), lon: +(Math.atan2(local.y, local.x) / DEG).toFixed(5) });
  });

  renderSources(assets);

  // ---------- Кадр ----------
  let prevNow = performance.now();
  renderer.setAnimationLoop((now) => {
    const dt = now - prevNow;
    prevNow = now;
    if (playing) {
      simMs += dt * Number($("system-speed").value);
      if (!fetching && now - lastFetch > 70) loadState(simMs);
      // орбіта Місяця помітно змінюється за добу (збурення) — оновлюємо, коли час відійшов на >12 год
      if (!orbitLoading && !(Math.abs(simMs - orbitMs) < 12 * 3600000)) loadOrbits(simMs, 0);
    }
    if (!state) { renderer.render(scene, camera); return; }

    // Розкладка з плавним переходом між режимами/масштабами
    let lay = layout(mode, scale, state);
    if (modeAnim?.from) {
      const t = Math.min(1, (now - modeAnim.t0) / 900);
      const e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      lay = lerpLayout(modeAnim.from, lay, e);
      if (t >= 1) modeAnim = null;
    }
    lastLayout = lay;

    // Орієнтації (Земля — з екстраполяцією обертання між запитами)
    const earthRot = rotateEarth(state.earth_orientation, EARTH_ROT_DEG_PER_DAY * (simMs - stateMs) / 86400000);
    const eM = bodyMatrix(earthRot, lay.earth.r, lay.earth.pos);
    const mM = bodyMatrix(state.moon_orientation, lay.moon.r, lay.moon.pos);
    earth.matrix.copy(eM.m);
    moon.matrix.copy(mM.m);
    sun.position.copy(lay.sun.pos);
    sun.scale.setScalar(lay.sun.r / sunModelRadius);
    glow.position.copy(lay.sun.pos);
    glow.scale.setScalar(lay.sun.r * 4.5);

    // Освітлення: справжні напрямки на Сонце від Землі й від Місяця
    const sunFromMoonKm = state.sun_km.map((v, i) => v - state.moon_km[i]);
    earth.material.uniforms.uSunDir.value.copy(dirScene(state.sun_km));
    moon.material.uniforms.uSunDir.value.copy(dirScene(sunFromMoonKm));

    updateOrbits(lay);
    const facts = updatePointAndStations(lay, earthRot, eM, mM, sunFromMoonKm);
    updateCamera(lay, now);
    controls.update();
    updateLabels(lay);
    updateFacts(facts);
    renderer.render(scene, camera);
  });

  // Точки орбіт у сцені (одиниці 1000 км, відносно центрального тіла) — рахуємо раз на відповідь API
  let orbitScene = null;
  let orbitSceneOf = null;
  function setLine(line, pts, center, k) {
    const n = pts.length;
    let attr = line.geometry.getAttribute("position");
    if (!attr || attr.count !== n) {
      attr = new THREE.BufferAttribute(new Float32Array(n * 3), 3);
      line.geometry.setAttribute("position", attr);
    }
    for (let i = 0; i < n; i++) attr.setXYZ(i, center.x + pts[i].x * k, center.y + pts[i].y * k, center.z + pts[i].z * k);
    attr.needsUpdate = true;
    line.geometry.computeBoundingSphere();
  }

  function updateOrbits(lay) {
    const showPath = $("system-path").checked;
    if (!orbitData) {
      for (const l of [moonOrbit, earthOrbit, moonPath, earthPath]) l.visible = false;
      return;
    }
    if (orbitSceneOf !== orbitData) {
      const conv = (arr) => arr.map((v) => toScene(v));
      orbitScene = {
        moon: conv(orbitData.moon.points_km), moonPath: conv(orbitData.moon.path_km),
        earth: conv(orbitData.earth.points_km), earthPath: conv(orbitData.earth.path_km),
      };
      orbitSceneOf = orbitData;
    }
    // Масштаб орбіти береться з поточної розкладки — орбіта завжди проходить через намальоване тіло
    // (і під час плавного переходу між режимами теж)
    const moonRel = toScene(state.moon_km);
    const kMoon = lay.moon.pos.distanceTo(lay.earth.pos) / moonRel.length();
    setLine(moonOrbit, orbitScene.moon, lay.earth.pos, kMoon);
    moonOrbit.visible = true;
    moonPath.visible = showPath;
    if (showPath) {
      setLine(moonPath, orbitScene.moonPath, lay.earth.pos, kMoon);
      moonPath.computeLineDistances();
      moonPath.material.dashSize = moonPath.material.gapSize = moonRel.length() * kMoon * 0.02;
    }
    const helio = mode !== "earth-moon";
    earthOrbit.visible = helio;
    earthPath.visible = helio && showPath;
    if (helio) {
      const sunRel = toScene(state.sun_km);
      const kEarth = lay.earth.pos.distanceTo(lay.sun.pos) / sunRel.length();
      setLine(earthOrbit, orbitScene.earth, lay.sun.pos, kEarth);
      if (showPath) {
        setLine(earthPath, orbitScene.earthPath, lay.sun.pos, kEarth);
        earthPath.computeLineDistances();
        earthPath.material.dashSize = earthPath.material.gapSize = sunRel.length() * kEarth * 0.01;
      }
    }
  }

  function updatePointAndStations(lay, earthRot, eM, mM, sunFromMoonKm) {
    const { lat, lon } = getState();
    const facts = {};
    const hasPoint = lat !== null && lon !== null;
    for (const o of [pointMarker, horizonDisk, toSunArrow, toEarthArrow]) o.visible = hasPoint;
    let pointScene = null;
    let earthUp = false;
    if (hasPoint) {
      const u = unitLatLon(lat, lon);
      const upScene = new THREE.Vector3(...apply3(mM.r, u)).normalize();
      pointScene = lay.moon.pos.clone().addScaledVector(upScene, lay.moon.r * 1.005);
      // Справжні вектори (ICRF, км): точка на поверхні, напрямки на Сонце й Землю
      const pIcrf = apply3(transpose(state.moon_orientation), u).map((v) => v * R_MOON * 1000);
      const toSun = dirScene(sunFromMoonKm.map((v, i) => v - pIcrf[i]));
      const toEarth = dirScene(state.moon_km.map((v, i) => -v - pIcrf[i]));
      const sunEl = Math.asin(THREE.MathUtils.clamp(upScene.dot(toSun), -1, 1)) / DEG;
      const earthEl = Math.asin(THREE.MathUtils.clamp(upScene.dot(toEarth), -1, 1)) / DEG;
      earthUp = earthEl > 0;
      const len = lay.moon.r * 1.7;
      for (const [arrow, dir] of [[toSunArrow, toSun], [toEarthArrow, toEarth]]) {
        arrow.position.copy(pointScene);
        arrow.setDirection(dir);
        arrow.setLength(len, len * 0.14, len * 0.06);
      }
      pointMarker.position.copy(pointScene);
      pointMarker.scale.setScalar(lay.moon.r * 0.035);
      horizonDisk.position.copy(pointScene);
      horizonDisk.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), upScene);
      horizonDisk.scale.setScalar(lay.moon.r * 0.4);
      facts.point = `${fmtLat(lat)}, ${fmtLon(lon)}: Сонце ${sunEl.toFixed(2)}°, Земля ${earthEl.toFixed(2)}° над матем. горизонтом`;
    }

    // DSN: кут Місяця над горизонтом станції (≥ мінімального кута антени — зв'язок можливий)
    const moonItrs = apply3(earthRot, state.moon_km);
    let best = null;
    const seeing = [];
    for (const st of stations) {
      const u = unitLatLon(st.lat, st.lon);
      const stKm = u.map((v) => v * R_EARTH * 1000);
      const d = moonItrs.map((v, i) => v - stKm[i]);
      const el = Math.asin((u[0] * d[0] + u[1] * d[1] + u[2] * d[2]) / Math.hypot(...d)) / DEG;
      const ok = el >= (st.min_elevation_deg ?? 10);
      const sceneUp = new THREE.Vector3(...apply3(eM.r, u)).normalize();
      st.mesh.position.copy(lay.earth.pos).addScaledVector(sceneUp, lay.earth.r * 1.01);
      st.mesh.scale.setScalar(lay.earth.r * 0.035);
      st.mesh.material.color.set(ok ? 0x8fd18f : 0x5b6170);
      st.el = el;
      st.visibleFace = sceneUp.dot(camera.position.clone().sub(st.mesh.position).normalize()) > 0.05;
      if (ok) {
        seeing.push(`${st.name.split(" (")[0]} ${el.toFixed(0)}°`);
        if (!best || el > best.el) best = st;
      }
    }
    facts.dsn = seeing.length ? seeing.join(", ") : "жодна (Місяць нижче 10° для всіх)";
    const showLink = Boolean(pointScene && best && earthUp);
    linkLine.visible = showLink;
    if (showLink) {
      linkLine.geometry.setFromPoints([pointScene, best.mesh.position]);
      linkLine.computeLineDistances();
      linkLine.material.dashSize = lay.moon.r * 0.6;
      linkLine.material.gapSize = lay.moon.r * 0.4;
    }
    return facts;
  }

  function focusFrame(lay) {
    if (focus === "overview") return lay.overview;
    if (focus === "moonview") {
      // Камера на лінії «Місяць → Земля»: Місяць видно так, як із центру Землі (справжня фаза).
      // Напрямок точний в обох масштабах: схематичний стискає лише довжину вектора Земля–Місяць.
      return { target: lay.moon.pos, dist: lay.moon.r * 4.5, dir: lay.earth.pos.clone().sub(lay.moon.pos).normalize() };
    }
    const b = lay[focus];
    return { target: b.pos, dist: b.r * (focus === "sun" ? 5 : 4.5) };
  }

  function updateCamera(lay, now) {
    const f = focusFrame(lay);
    const body = focus === "overview" ? "earth" : focus === "moonview" ? "moon" : focus;
    controls.minDistance = lay[body].r * 1.15;
    controls.maxDistance = 3e6;
    controls.enableRotate = !f.dir; // у вигляді «з Землі» напрямок зафіксовано, лишається масштаб
    if (camAnim) {
      const t = Math.min(1, (now - camAnim.t0) / 900);
      const e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      const dir = camAnim.fromOffset.lengthSq() > 0 ? camAnim.fromOffset.clone().normalize() : new THREE.Vector3(0.3, 0.45, 1).normalize();
      if (f.dir) {
        // поворот кватерніоном: працює й для майже протилежних напрямків (lerp пройшов би через нуль)
        const q = new THREE.Quaternion().setFromUnitVectors(dir.clone(), f.dir);
        dir.applyQuaternion(new THREE.Quaternion().slerp(q, e));
      }
      const fromDist = camAnim.fromOffset.length();
      const dist = fromDist + (f.dist - fromDist) * e;
      controls.target.lerpVectors(camAnim.fromTarget, f.target, e);
      camera.position.copy(controls.target).addScaledVector(dir, dist);
      if (t >= 1) camAnim = null;
      return;
    }
    if (f.dir) {
      const dist = camera.position.distanceTo(controls.target); // до зсуву: зберігаємо масштаб користувача
      controls.target.copy(f.target);
      camera.position.copy(f.target).addScaledVector(f.dir, dist);
      return;
    }
    // Слідуємо за тілом: зсуваємо ціль і камеру разом (кут огляду лишається)
    const delta = f.target.clone().sub(controls.target);
    controls.target.add(delta);
    camera.position.add(delta);
  }

  function updateLabels(lay) {
    const w = host.clientWidth, h = host.clientHeight;
    const place = (el, pos, offsetR) => {
      const p = pos.clone();
      const s = p.project(camera);
      const vis = s.z < 1 && Math.abs(s.x) < 1.05 && Math.abs(s.y) < 1.05;
      el.style.display = vis ? "" : "none";
      if (vis) el.style.transform = `translate(${((s.x + 1) / 2) * w + 6}px, ${((1 - s.y) / 2) * h - 6 - offsetR}px)`;
    };
    for (const k of ["sun", "earth", "moon"]) place(labels[k], lay[k].pos, 0);
    // Підписи станцій — лише коли Земля на екрані більша за ~40 px, інакше вони злипаються з «Земля»/«Місяць»
    const dist = Math.max(camera.position.distanceTo(lay.earth.pos), 1e-6);
    const earthPx = (lay.earth.r / (dist * Math.tan((camera.fov * DEG) / 2))) * (h / 2);
    for (const st of stations) {
      st.label ??= makeLabel(st.name.split(" (")[0], "dsn");
      st.label.classList.toggle("off", !(st.el >= (st.min_elevation_deg ?? 10)));
      if (st.visibleFace && earthPx > 40) place(st.label, st.mesh.position, 0);
      else st.label.style.display = "none";
    }
  }

  function updateFacts(facts) {
    const set = (k, v) => { const el = document.querySelector(`[data-fact="${k}"]`); if (el) el.textContent = v; };
    const dKm = Math.hypot(...state.moon_km);
    set("datetime", playing ? isoUtc(simMs).replace("T", " ") : state.datetime.replace("T", " "));
    set("distance", `${fmtKm(dKm)} (світло ${(dKm / C_KM_S).toFixed(3)} с)`);
    const ill = state.moon_illumination;
    if (ill) {
      // Зростаючий: екліптична довгота Місяця − Сонця в (0°, 180°)
      const m = toScene(state.moon_km), s = toScene(state.sun_km);
      const elong = ((Math.atan2(-m.z, m.x) - Math.atan2(-s.z, s.x)) / DEG + 360) % 360;
      set("phase", `${phaseName(ill.fraction, elong < 180)}, освітлено ${(ill.fraction * 100).toFixed(1)}%`);
    }
    if (state.earth_sub_solar_point) set("earth_sun", `${fmtLat(state.earth_sub_solar_point.lat)}, ${fmtLon(state.earth_sub_solar_point.lon)}`);
    if (state.earth_sub_lunar_point) set("earth_moon", `${fmtLat(state.earth_sub_lunar_point.lat)}, ${fmtLon(state.earth_sub_lunar_point.lon)}`);
    set("moon_sun", `${fmtLat(state.sub_solar_point.lat)}, ${fmtLon(state.sub_solar_point.lon)}`);
    set("point", facts.point ?? "не вибрано (клік по Місяцю)");
    set("dsn", facts.dsn);
    if (orbitData) {
      const m = orbitData.moon.elements, e = orbitData.earth.elements;
      set("orbit_moon", `a = ${fmtKm(m.a_km)}, e = ${m.e.toFixed(4)}, нахил ${m.inclination_deg.toFixed(2)}°, ` +
        `перигей ${fmtKm(m.periapsis_km)}, апогей ${fmtKm(m.apoapsis_km)}; справжній шлях відходить до ${fmtKm(orbitData.moon.max_deviation_km)}`);
      set("orbit_earth", `a = ${(e.a_km / 149597870.7).toFixed(6)} а.о., e = ${e.e.toFixed(5)}, період ${e.period_days.toFixed(2)} д; ` +
        `відхилення за рік до ${fmtKm(orbitData.earth.max_deviation_km)}`);
    }
  }

  // Перше завантаження: погляд під кутом ~25° до площини екліптики
  camera.position.set(400, 450, 1000);
  setFocus("overview");
  await loadState(simMs);
  loadOrbits(simMs);
}

function renderSources(assets) {
  const list = $("system-sources");
  if (!list) return;
  const items = [];
  if (assets) {
    const { sun, earth } = assets.assets;
    items.push([`Сонце: «Sun 3D Model» (glTF), ${sun.credit}. ${sun.note}`, sun.page]);
    items.push([`Земля: «Earth (A)», ${earth.credit}. ${earth.note}`, earth.page]);
  } else {
    items.push(["Моделі NASA не підготовлено — запустіть python tools/build_system_assets.py; поки тіла однотонні", "https://science.nasa.gov/3d-resources/"]);
  }
  items.push(["Місяць: CGI Moon Kit (LRO LROC WAC + LOLA), NASA SVS", "https://svs.gsfc.nasa.gov/4720"]);
  items.push(["Положення Сонця, Землі й Місяця: JPL DE440; орієнтація Місяця — IAU 2015; Землі — ICRF→ITRS (skyfield). Звірено з JPL Horizons (≤ 0,01°)", "https://ssd.jpl.nasa.gov/horizons/"]);
  items.push(["Рамка сцени — екліптика J2000 (нахил 23,4392911°). Схематичний масштаб: тіла збільшено, відстані стиснуто; напрямки, повороти й освітлення — справжні", "https://ssd.jpl.nasa.gov/planets/eph_export.html"]);
  items.push(["Станції DSN і мінімальний кут антени 10° — каталог проєкту (app/data/dsn_stations.json)", "https://www.nasa.gov/directorates/somd/space-communications-navigation-program/deep-space-network/"]);
  list.replaceChildren(...items.map(([text, href]) => {
    const li = document.createElement("li");
    li.append(text + " — ");
    const a = document.createElement("a");
    a.href = href; a.target = "_blank"; a.rel = "noopener"; a.textContent = "джерело";
    li.append(a);
    return li;
  }));
}

main();
