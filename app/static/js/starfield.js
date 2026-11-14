// Зоряне небо на тлі сторінки — «середовище», у якому стоять наші планети. Джерело текстури за пріоритетом:
//   1) панорама Чумацького Шляху (GLB користувача → tools/import_sky_pano.py; CC BY-NC-SA 4.0, автор MozillaHubs),
//      орієнтація калібрується за галактичною площиною (оцінка, не астрометрія);
//   2) карта NASA SVS «Deep Star Maps 2020» (Hipparcos-2, Tycho-2, Gaia DR2; ICRF/J2000; орієнтація перевірена за зорями).
// Небо приглушене (фон не відволікає від інтерфейсу) і прив'язане до камери активної 3D-сцени: коли користувач
// обертає глобус, систему чи вид з поверхні, зорі повертаються разом із ним — з тією самою орієнтацією, що й тіла сцени.
// При віддаленні від планети небо ледь помітно зсувається (паралакс «з орбіти»).
//
// Як це працює: окремий повноекранний canvas (WebGL2) малює один трикутник; фрагментний шейдер для кожного пікселя
// будує напрям променя в системі камери, повертає його матрицею «камера → сцена → ICRF» і шукає в карті колір за
// прямим сходженням і схиленням. Жодної геометрії, тож немає швів і спотворень на краях екрана.
//
// Орієнтація сцени відносно ICRF (кожен вид задає свою матрицю):
//   • система Сонце–Земля–Місяць: ICRF → екліптика → осі Three.js (system_view.js);
//   • глобус і вид з поверхні: ICRF → власна система Місяця (MOON_ME, /api/system.moon_orientation) → осі виду.
// Без файлу карти (tools/build_starmap.py) нічого не ламається: лишається CSS-тло (css/cosmos.css).
import { t } from "./i18n.js";
import { getState, subscribe } from "./state.js";

export const STARMAP_URL = "/assets/starmap/starmap.jpg";
export const PANO_URL = "/assets/starmap/pano.jpg";
export const PANO_META_URL = "/assets/starmap/pano.json";
const DEG = Math.PI / 180;

// Як лягає текстура на небо: sign — напрям RA по осі x (+1 вправо, −1 вліво), centerDeg — RA в центрі кадру,
// exposure — приглушення (множник яскравості). Карта NASA: RA ліворуч, 0h по центру (опис SVS 4851).
export const NASA_MAP = Object.freeze({ url: STARMAP_URL, sign: -1, centerDeg: 0, exposure: 0.8, credit: null });
export const DIM_EXPOSURE = 0.6; // «трошки затемнити» панораму, щоб небо не відволікало від інтерфейсу

/** Налаштування панорами з pano.json (див. tools/import_sky_pano.py); null — без калібрування не використовуємо. */
export function panoConfig(meta) {
  const o = meta?.orientation;
  if (!o || !Number.isFinite(o.ra_center_deg) || !["left", "right"].includes(o.ra_direction) || o.north !== "up") return null;
  return Object.freeze({ url: PANO_URL, sign: o.ra_direction === "right" ? 1 : -1, centerDeg: o.ra_center_deg, exposure: DIM_EXPOSURE, credit: meta.credit ?? null });
}

// ---------- Чиста математика (перевіряється в Node) ----------
export const IDENTITY3 = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
export const mul3 = (a, b) => a.map((row) => [0, 1, 2].map((j) => row[0] * b[0][j] + row[1] * b[1][j] + row[2] * b[2][j]));
export const transpose3 = (m) => [0, 1, 2].map((i) => [m[0][i], m[1][i], m[2][i]]);
export const apply3 = (m, v) => m.map((row) => row[0] * v[0] + row[1] * v[1] + row[2] * v[2]);

// Кватерніон (x, y, z, w) → матриця повороту 3×3 (камера → сцена).
export function quatToMat3([x, y, z, w]) {
  const xx = x * x, yy = y * y, zz = z * z, xy = x * y, xz = x * z, yz = y * z, wx = w * x, wy = w * y, wz = w * z;
  return [
    [1 - 2 * (yy + zz), 2 * (xy - wz), 2 * (xz + wy)],
    [2 * (xy + wz), 1 - 2 * (xx + zz), 2 * (yz - wx)],
    [2 * (xz - wy), 2 * (yz + wx), 1 - 2 * (xx + yy)],
  ];
}

// Напрям ICRF → пряме сходження й схилення, градуси: RA ∈ [0, 360), Dec ∈ [−90, 90].
export function raDec(dir) {
  const n = Math.hypot(dir[0], dir[1], dir[2]);
  const ra = Math.atan2(dir[1], dir[0]) / DEG;
  return { ra: (ra + 360) % 360, dec: Math.asin(Math.max(-1, Math.min(1, dir[2] / n))) / DEG };
}

// Напрям ICRF → координати текстури: 0h по центру, RA збільшується ліворуч, північ угорі (опис карти на SVS 4851).
// u, v ∈ [0, 1]; v = 0 — верхній рядок зображення. Той самий розрахунок — у шейдері.
export function skyUv(dir, map = NASA_MAP) {
  const { ra, dec } = raDec(dir);
  const rel = ((((ra - map.centerDeg) % 360) + 540) % 360) - 180; // RA відносно центру кадру, −180…180
  return { u: 0.5 + (map.sign * rel) / 360, v: 0.5 - dec / 180 };
}

// Паралакс «з орбіти»: небо ледь повертається, коли камера відходить від планети або наближається. Кут — лише
// log-відстань, обмежений: perEfold градусів на кожне збільшення відстані в e разів, не більше maxDeg.
export function parallaxAngleDeg(distance, reference, perEfold = 2.5, maxDeg = 6) {
  if (!(distance > 0) || !(reference > 0)) return 0;
  return Math.max(-maxDeg, Math.min(maxDeg, perEfold * Math.log(distance / reference)));
}

// Поворот навколо осі y камери (вертикаль екрана) на кут, рад.
export const rotY = (a) => [[Math.cos(a), 0, Math.sin(a)], [0, 1, 0], [-Math.sin(a), 0, Math.cos(a)]];

// Власна система Місяця (x — на 0° довготи, y — на схід, z — на північ) → осі глобуса: (cosφ·sinλ, sinφ, cosφ·cosλ).
export const ME_TO_GLOBE = [[0, 1, 0], [0, 0, 1], [1, 0, 0]];

// Власна система Місяця → осі вигляду з поверхні в точці (φ, λ): рядки — схід, північ, зеніт у ME; потім ті ж
// напрями у сцені виду (east, north, up — осі сцени, у якій малює surface_view.js).
export function meToSurface(latDeg, lonDeg, sceneEast, sceneNorth, sceneUp) {
  const la = latDeg * DEG, lo = lonDeg * DEG;
  const e = [-Math.sin(lo), Math.cos(lo), 0];
  const n = [-Math.sin(la) * Math.cos(lo), -Math.sin(la) * Math.sin(lo), Math.cos(la)];
  const u = [Math.cos(la) * Math.cos(lo), Math.cos(la) * Math.sin(lo), Math.sin(la)];
  // сцена = East_s·(e·v) + North_s·(n·v) + Up_s·(u·v)
  return [0, 1, 2].map((r) => [0, 1, 2].map((c) => sceneEast[r] * e[c] + sceneNorth[r] * n[c] + sceneUp[r] * u[c]));
}

// Матриця для шейдера: напрям у системі камери → ICRF. frame — матриця ICRF → сцена.
export function cameraToIcrf(quat, frame) {
  return mul3(transpose3(frame), quatToMat3(quat));
}

// ---------- Привʼязка до сцен ----------
const bindings = new Set(); // { camera, host, frame(orientation) → матриця ICRF → сцена }
let orientation = null; // ICRF → MOON_ME, 3×3 (відповідь /api/system)

/** Привʼязати небо до камери сцени. frame(orientationMoon|null) → матриця 3×3 «ICRF → сцена». Повертає відв'язування. */
export function bindSky(camera, host, frame, { controls = null, parallax = true } = {}) {
  const b = { camera, host, frame, controls, parallax, angle: 0, ref: null };
  bindings.add(b);
  return () => bindings.delete(b);
}

/** Останній кадр неба (для діагностики й тестів у браузері): матриця камера→ICRF, tan(fov/2), центр кадру в RA/Dec. */
export const lastFrame = { m: null, tan: null, center: null, bound: 0 };

let timeAbort = null;
let timeTimer = null;
const orientationCache = new Map();

/** Момент, для якого береться орієнтація Місяця (ISO або мс); викликається при зміні дати й руху повзунка часу. */
export function setSkyTime(when, { immediate = false } = {}) {
  const iso = new Date(typeof when === "number" ? when : Date.parse(when)).toISOString().slice(0, 16) + ":00Z";
  const run = async () => {
    if (orientationCache.has(iso)) { orientation = orientationCache.get(iso); return; }
    timeAbort?.abort();
    timeAbort = new AbortController();
    try {
      const res = await fetch(`/api/system?${new URLSearchParams({ datetime: iso })}`, { signal: timeAbort.signal });
      const data = await res.json();
      if (res.ok && Array.isArray(data.moon_orientation)) {
        orientation = data.moon_orientation;
        orientationCache.set(iso, orientation);
        if (orientationCache.size > 200) orientationCache.delete(orientationCache.keys().next().value);
      }
    } catch { /* без орієнтації небо лишається в останньому положенні */ }
  };
  clearTimeout(timeTimer);
  if (immediate) run(); else timeTimer = setTimeout(run, 120);
}

// ---------- Малювання ----------
const VERT = `#version 300 es
in vec2 aPos; out vec2 vNdc;
void main() { vNdc = aPos; gl_Position = vec4(aPos, 0.0, 1.0); }`;

const FRAG = `#version 300 es
precision highp float;
in vec2 vNdc; out vec4 outColor;
uniform sampler2D uMap; uniform mat3 uM; uniform vec2 uTan; uniform float uExposure; uniform float uRaCenter; uniform float uSign;
const float PI = 3.14159265358979;
void main() {
  vec3 d = normalize(uM * vec3(vNdc.x * uTan.x, vNdc.y * uTan.y, -1.0));
  float ra = atan(d.y, d.x) - uRaCenter;
  ra -= 2.0 * PI * floor((ra + PI) / (2.0 * PI));     // −π…π відносно центру кадру
  float u = 0.5 + uSign * ra / (2.0 * PI);            // напрям RA і центр — з налаштувань текстури
  float v = 0.5 - asin(clamp(d.z, -1.0, 1.0)) / PI;   // північ угорі
  // шов атан(): беремо варіант u з меншою похідною, щоб рівень мипмапу не стрибав на RA = ±180°
  float u2 = fract(u + 0.5) - 0.5;
  float uu = fwidth(u) <= fwidth(u2) + 1e-6 ? u : u2;
  vec3 c = texture(uMap, vec2(uu, v)).rgb * uExposure;
  outColor = vec4(c, 1.0);
}`;

function compile(gl, type, src) {
  const s = gl.createShader(type);
  gl.shaderSource(s, src); gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) || "shader");
  return s;
}

const loadImage = (url) => new Promise((resolve, reject) => {
  const img = new Image();
  img.decoding = "async";
  img.onload = () => resolve(img);
  img.onerror = reject;
  img.src = url;
});

// Панорама (якщо імпортована й відкалібрована) → карта NASA → нічого (лишається CSS-тло).
async function pickSky() {
  try {
    const res = await fetch(PANO_META_URL);
    const cfg = res.ok ? panoConfig(await res.json()) : null;
    if (cfg) return { cfg, img: await loadImage(cfg.url) };
  } catch { /* панорами немає */ }
  try { return { cfg: NASA_MAP, img: await loadImage(NASA_MAP.url) }; } catch { return null; }
}

// Подяка автору (умова CC BY-NC-SA): невеликий підпис унизу сторінки з посиланням на джерело.
function showCredit(credit) {
  if (!credit?.title) return;
  const a = document.createElement("a");
  a.className = "sky-credit";
  a.href = credit.source || "#";
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  const author = String(credit.author || "").replace(/\s*\(.*\)\s*$/, "");
  a.textContent = `${t("Небо")}: «${credit.title}», ${author}, CC BY-NC-SA 4.0`;
  a.title = credit.license || "";
  document.body.append(a);
}

async function start() {
  const canvas = document.createElement("canvas");
  canvas.id = "starfield";
  canvas.setAttribute("aria-hidden", "true");
  const gl = canvas.getContext("webgl2", { antialias: false, alpha: false, powerPreference: "low-power" });
  if (!gl) return; // лишається CSS-тло
  const sky = await pickSky();
  if (!sky) return; // карт немає (tools/build_starmap.py, tools/import_sky_pano.py) — CSS-тло
  try { run(canvas, gl, sky.img, sky.cfg); showCredit(sky.cfg.credit); } catch (err) { console.warn("starfield:", err); }
}

function run(canvas, gl, img, cfg) {
  const prog = gl.createProgram();
  gl.attachShader(prog, compile(gl, gl.VERTEX_SHADER, VERT));
  gl.attachShader(prog, compile(gl, gl.FRAGMENT_SHADER, FRAG));
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog) || "link");
  gl.useProgram(prog);
  const buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(prog, "aPos");
  gl.enableVertexAttribArray(loc);
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  const tex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, tex);
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB8, gl.RGB, gl.UNSIGNED_BYTE, img);
  gl.generateMipmap(gl.TEXTURE_2D);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  const aniso = gl.getExtension("EXT_texture_filter_anisotropic");
  if (aniso) gl.texParameterf(gl.TEXTURE_2D, aniso.TEXTURE_MAX_ANISOTROPY_EXT, 4);
  const U = Object.fromEntries(["uMap", "uM", "uTan", "uExposure", "uRaCenter", "uSign"].map((n) => [n, gl.getUniformLocation(prog, n)]));
  gl.uniform1i(U.uMap, 0);
  gl.uniform1f(U.uExposure, cfg.exposure);
  gl.uniform1f(U.uRaCenter, cfg.centerDeg * DEG);
  gl.uniform1f(U.uSign, cfg.sign);

  document.body.prepend(canvas);
  document.body.classList.add("has-starfield");

  const resize = () => {
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    const w = Math.max(1, Math.round(window.innerWidth * dpr)), h = Math.max(1, Math.round(window.innerHeight * dpr));
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; gl.viewport(0, 0, w, h); }
  };
  window.addEventListener("resize", resize);
  resize();

  // орієнтація за замовчуванням (немає активної сцени): північ угорі, дивимося на RA 0h
  const idleFrame = IDENTITY3;
  // сцена видима: у документі, має розмір і не приховане (visibility: hidden — так ховають глобус під видом з поверхні);
  // offsetParent для position: fixed завжди null, тож ним не користуємося
  const shown = (host) => host?.isConnected && host.clientWidth > 0 && host.clientHeight > 0
    && (typeof host.checkVisibility === "function" ? host.checkVisibility({ visibilityProperty: true }) : getComputedStyle(host).visibility !== "hidden");
  const active = () => [...bindings].reverse().find((b) => shown(b.host));
  let last = "";
  function frame() {
    const b = active();
    let m, tan = 0.4142;
    if (b) {
      const q = b.camera.quaternion;
      m = cameraToIcrf([q.x, q.y, q.z, q.w], b.frame(orientation) ?? idleFrame);
      if (b.parallax) { // ледь помітний зсув неба при зміні відстані до планети; згладжено, щоб не смикалось
        const dist = b.controls ? b.camera.position.distanceTo(b.controls.target) : b.camera.position.length();
        b.ref ??= dist;
        b.angle += (parallaxAngleDeg(dist, b.ref) - b.angle) * 0.12;
        m = mul3(m, rotY(b.angle * DEG));
      }
      tan = Math.tan((b.camera.fov * DEG) / 2);
    } else {
      m = idleFrame;
    }
    const aspect = canvas.width / canvas.height;
    lastFrame.m = m; lastFrame.tan = tan; lastFrame.bound = bindings.size;
    lastFrame.center = raDec(apply3(m, [0, 0, -1]));
    const key = `${m.flat().map((v) => v.toFixed(5)).join()}|${tan.toFixed(4)}|${aspect.toFixed(3)}`;
    if (key !== last) {
      last = key;
      // uniformMatrix3fv приймає стовпці: віддаємо транспоновану, тож отримуємо саме m
      const t = transpose3(m).flat();
      gl.uniformMatrix3fv(U.uM, false, new Float32Array(t));
      gl.uniform2f(U.uTan, tan * aspect, tan);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }
  }
  // rAF + запасний таймер: у прихованій панелі rAF стоїть, а небо має встигати за камерою (як в інших модулях)
  let raf = 0, timer = 0;
  function tick() {
    cancelAnimationFrame(raf); clearTimeout(timer);
    frame();
    raf = requestAnimationFrame(tick);
    timer = setTimeout(tick, 120);
  }
  tick();
}

if (typeof document !== "undefined" && typeof window !== "undefined") {
  const init = () => {
    start();
    setSkyTime(getState().datetime, { immediate: true });
    subscribe((st) => setSkyTime(st.datetime));
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true }); else init();
}
