// Місячний ґрунт (реголіт) для виду з поверхні: мікрорельєф, що реагує на справжнє Сонце, і колір з реальної карти.
//
// Що тут справжнє, а що ні (чесно):
//   • колір (відтінок) ґрунту — з текстури CGI Moon Kit (LRO LROC WAC, NASA SVS) у координатах точки; роздільність карти
//     — кілометри на піксель;
//   • освітлення й тіні великого рельєфу — не тут: їх дає lightGrid (DEM LOLA, справжнє положення Сонця), текстура лише
//     множить їх;
//   • мікрорельєф (камінці, кратери від сантиметрів до десятків метрів) — процедурний: знімків такої роздільності для
//     конкретної точки немає. Він не є знімком місця, але освітлюється тим самим Сонцем: на низькому Сонці дрібні
//     кратери й камені дають довгі тіні, на високому — майже зникають, як на справжніх знімках Місяця.
//
// Як це влаштовано: три тайлові шари (плитки 14 м, 110 м і 900 м) з картою альбедо й картою нахилів (RGBA: R — альбедо,
// G, B — нахили на схід і північ). Шейдер збирає нахил усіх шарів, будує нормаль і рахує освітленість мікрорельєфу відносно
// гладкої поверхні для напряму Сонця; вдалині деталь згасає (мипмапи + плавний перехід).

export const NEAR_TILE_M = 2.3; // ближній шар: та сама текстура зерна, але плитка 2,3 м (≈ 1 см на піксель текстури)
export const TILE_METERS = 96; // залишено для сумісності: розмір опорної плитки, м (шари мають власні розміри)

/** Параметри шарів. tileM — розмір плитки на ґрунті, м; slope — цільовий нахил (95-й перцентиль, безрозмірний). */
export const GROUND_LAYERS = Object.freeze([
  { name: "grain", tileM: 14, size: 256, seed: 11, slope: 0.55, noise: [[8, 0.30], [16, 0.30], [32, 0.25], [64, 0.15]],
    craters: { count: 70, rMin: 1.5, rMax: 7, depth: 0.2 }, pebbles: 700 },
  { name: "craters", tileM: 110, size: 256, seed: 23, slope: 0.42, noise: [[4, 0.4], [8, 0.3], [16, 0.2], [32, 0.1]],
    craters: { count: 40, rMin: 3, rMax: 26, depth: 0.2 }, pebbles: 120 },
  { name: "basins", tileM: 900, size: 256, seed: 37, slope: 0.28, noise: [[2, 0.5], [4, 0.3], [8, 0.2]],
    craters: { count: 24, rMin: 5, rMax: 46, depth: 0.16 }, pebbles: 0 },
]);

// Детермінований генератор (mulberry32): однакова текстура в кожному запуску й у тестах.
export function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const smooth = (t) => t * t * (3 - 2 * t);
const wrap = (v, n) => ((v % n) + n) % n;

// Періодичний шум значень: решітка period×period випадкових чисел, білінійно з плавною кривою; стик країв точний.
function valueNoise(size, period, rand) {
  const grid = Float32Array.from({ length: period * period }, () => rand());
  const out = new Float32Array(size * size);
  for (let y = 0; y < size; y++) {
    const fy = (y / size) * period, y0 = Math.floor(fy), ty = smooth(fy - y0);
    for (let x = 0; x < size; x++) {
      const fx = (x / size) * period, x0 = Math.floor(fx), tx = smooth(fx - x0);
      const g = (i, j) => grid[wrap(j, period) * period + wrap(i, period)];
      const a = g(x0, y0) + (g(x0 + 1, y0) - g(x0, y0)) * tx;
      const b = g(x0, y0 + 1) + (g(x0 + 1, y0 + 1) - g(x0, y0 + 1)) * tx;
      out[y * size + x] = a + (b - a) * ty;
    }
  }
  return out;
}

/**
 * Один тайловий шар: висота (в текселях), альбедо 0,78…1,0 і нахили gx (схід), gy (північ) у межах −1…1.
 * Нахили нормовано так, щоб 95-й перцентиль модуля нахилу дорівнював spec.slope (дрібні й великі шари порівнянні).
 * Краї замкнені (індекси за модулем), тож плитки стикуються без швів.
 */
export function regolithLayer(spec) {
  const n = spec.size, rand = rng(spec.seed);
  const h = new Float32Array(n * n), albedo = new Float32Array(n * n);
  for (const [period, weight] of spec.noise) {
    const f = valueNoise(n, period, rand);
    for (let i = 0; i < h.length; i++) { h[i] += (f[i] - 0.5) * weight; albedo[i] += (f[i] - 0.5) * weight * 0.5; }
  }
  // висоти від шуму — у «текселях»: масштаб підбираємо відносно кратерів, щоб шум не заглушав їх
  const noiseScale = spec.craters.rMax * 0.18;
  for (let i = 0; i < h.length; i++) h[i] *= noiseScale;
  const stamp = (cx, cy, r, depth, brighten) => { // кратер: чаша, піднятий вал, світліший викид
    const R = Math.ceil(r * 1.7);
    for (let dy = -R; dy <= R; dy++) {
      for (let dx = -R; dx <= R; dx++) {
        const d = Math.hypot(dx, dy) / r;
        if (d > 1.7) continue;
        let dh = 0, da = 0;
        if (d < 1) { dh = -depth * r * (1 - d * d); da = -0.05 * (1 - d); }
        else if (d < 1.5) { const k = 1 - (d - 1) / 0.5; dh = 0.34 * depth * r * k * k; da = brighten * k; }
        else { da = brighten * 0.25 * (1.7 - d) / 0.2; }
        const idx = wrap(cy + dy, n) * n + wrap(cx + dx, n);
        h[idx] += dh; albedo[idx] += da;
      }
    }
  };
  const { count, rMin, rMax, depth } = spec.craters;
  for (let i = 0; i < count; i++) {
    const t = rand() ** 2.2; // багато малих, мало великих (степеневий розподіл розмірів)
    stamp(Math.floor(rand() * n), Math.floor(rand() * n), rMin + (rMax - rMin) * t, depth * (0.7 + 0.5 * rand()), 0.05 + 0.08 * rand());
  }
  for (let i = 0; i < spec.pebbles; i++) { // камінці: невеликі пагорби з світлішою верхівкою
    const cx = Math.floor(rand() * n), cy = Math.floor(rand() * n), r = 1.3 + rand() * 1.7, ht = 0.8 + rand() * 1.8;
    for (let dy = -4; dy <= 4; dy++) {
      for (let dx = -4; dx <= 4; dx++) {
        const d2 = (dx * dx + dy * dy) / (r * r);
        if (d2 > 5) continue;
        const idx = wrap(cy + dy, n) * n + wrap(cx + dx, n);
        h[idx] += ht * Math.exp(-d2); albedo[idx] += 0.09 * Math.exp(-d2);
      }
    }
  }
  // легке згладжування (ядро 3×3 з обгортанням): без нього при збільшенні видно квадрати розміром у піксель текстури
  const blurred = new Float32Array(n * n);
  for (let y = 0; y < n; y++) {
    for (let x = 0; x < n; x++) {
      let sum = 0;
      for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) sum += h[wrap(y + dy, n) * n + wrap(x + dx, n)] * (dx === 0 && dy === 0 ? 2 : 1);
      blurred[y * n + x] = sum / 10;
    }
  }
  h.set(blurred);
  // нахили центральними різницями (з обгортанням), далі нормування до цільового 95-го перцентиля
  const gx = new Float32Array(n * n), gy = new Float32Array(n * n), mag = new Float32Array(n * n);
  for (let y = 0; y < n; y++) {
    for (let x = 0; x < n; x++) {
      const k = y * n + x;
      gx[k] = (h[y * n + wrap(x + 1, n)] - h[y * n + wrap(x - 1, n)]) / 2;
      gy[k] = (h[wrap(y + 1, n) * n + x] - h[wrap(y - 1, n) * n + x]) / 2;
      mag[k] = Math.hypot(gx[k], gy[k]);
    }
  }
  const sorted = Float32Array.from(mag).sort();
  const p95 = sorted[Math.floor(sorted.length * 0.95)] || 1;
  const scale = spec.slope / p95;
  for (let k = 0; k < gx.length; k++) {
    gx[k] = Math.max(-1, Math.min(1, gx[k] * scale));
    gy[k] = Math.max(-1, Math.min(1, gy[k] * scale));
  }
  let lo = Infinity, hi = -Infinity;
  for (const v of albedo) { if (v < lo) lo = v; if (v > hi) hi = v; }
  const span = hi - lo || 1;
  for (let k = 0; k < albedo.length; k++) albedo[k] = 0.78 + 0.22 * ((albedo[k] - lo) / span);
  return { size: n, albedo, gx, gy };
}

/** Колір ґрунту з усередненого пікселя реальної карти: відтінок без зміни яскравості (її дає освітлення). */
export function tintFromRgb(r, g, b, strength = 0.6) {
  const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  if (!(lum > 1e-6)) return [1, 1, 1];
  const mix = (c) => 1 + (c / lum - 1) * strength;
  const clamp = (v) => Math.min(1.25, Math.max(0.8, v));
  return [clamp(mix(r)), clamp(mix(g)), clamp(mix(b))];
}

/** Піксель карти Moon Kit у точці: рівнопроміжна проєкція, довгота 0° по центру, північ угорі. */
export function moonMapPixel(width, height, latDeg, lonDeg) {
  const lon = ((((lonDeg + 180) % 360) + 360) % 360);
  return { x: Math.min(width - 1, Math.floor((lon / 360) * width)), y: Math.min(height - 1, Math.max(0, Math.floor((0.5 - latDeg / 180) * height))) };
}

/** Колір ґрунту в точці з /assets/globe/color.jpg; [1, 1, 1] (без відтінку), якщо карти немає. */
export async function sampleMoonTint(latDeg, lonDeg, url = "/assets/globe/color.jpg") {
  try {
    const img = new Image();
    img.crossOrigin = "anonymous";
    await new Promise((resolve, reject) => { img.onload = resolve; img.onerror = reject; img.src = url; });
    const c = document.createElement("canvas");
    c.width = img.naturalWidth; c.height = img.naturalHeight;
    const g = c.getContext("2d", { willReadFrequently: true });
    g.drawImage(img, 0, 0);
    const { x, y } = moonMapPixel(c.width, c.height, latDeg, lonDeg);
    const r = 4, x0 = Math.max(0, x - r), y0 = Math.max(0, y - r);
    const w = Math.min(c.width - x0, 2 * r + 1), h = Math.min(c.height - y0, 2 * r + 1);
    const d = g.getImageData(x0, y0, w, h).data;
    let R = 0, G = 0, B = 0;
    for (let i = 0; i < d.length; i += 4) { R += d[i]; G += d[i + 1]; B += d[i + 2]; }
    const n = d.length / 4;
    return tintFromRgb(R / n, G / n, B / n);
  } catch { return [1, 1, 1]; }
}

// ---------- Шейдер ґрунту ----------
export const GROUND_VERT = `
attribute vec3 aLight;      // освітленість вершини від DEM (великий рельєф, тіні, підсвітка)
varying vec3 vLight; varying vec2 vMeters; varying vec3 vPos;
void main() {
  vLight = aLight; vMeters = uv; vPos = position;   // uv — метри на ґрунті (схід, північ)
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

export const GROUND_FRAG = `
precision highp float;
uniform sampler2D uT0; uniform sampler2D uT1; uniform sampler2D uT2;
uniform vec3 uTile;         // розміри плиток, м; ближній шар береться з текстури зерна з плиткою uNear
uniform vec3 uSun;          // напрям на Сонце в осях сцени (x — схід, y — угору, z — на південь)
uniform vec3 uTint; uniform float uUnit;   // колір ґрунту з карти; метрів у одиниці сцени
uniform float uNear;        // плитка ближнього шару, м
varying vec3 vLight; varying vec2 vMeters; varying vec3 vPos;
void main() {
  vec4 a = texture2D(uT0, vMeters / uTile.x);
  vec4 b = texture2D(uT1, vMeters / uTile.y + vec2(0.37, 0.11));
  vec4 c = texture2D(uT2, vMeters / uTile.z + vec2(0.71, 0.53));
  vec2 q = mat2(0.8, -0.6, 0.6, 0.8) * vMeters / uNear;                      // повернуто, щоб не збігалось з основною плиткою
  vec4 d = texture2D(uT0, q + vec2(0.19, 0.83));
  float albedo = clamp(a.r * b.r * c.r * mix(1.0, d.r * 1.15, 0.6) * 1.12, 0.0, 1.1);
  vec2 g = (a.gb * 2.0 - 1.0) + 0.8 * (b.gb * 2.0 - 1.0) + 0.6 * (c.gb * 2.0 - 1.0) + 0.7 * (d.gb * 2.0 - 1.0);
  vec3 n = normalize(vec3(-g.x, 1.0, g.y));               // z — на південь, тож нахил на північ дає +z
  float up = max(uSun.y, 0.0);
  float shade = up > 0.0 ? (max(dot(n, uSun), 0.0) + 0.12) / (up + 0.12) : 1.0;   // відносно гладкої поверхні
  float fade = smoothstep(250.0, 2500.0, distance(vPos, cameraPosition) * uUnit);   // вдалині деталь згасає
  shade = mix(clamp(shade, 0.25, 1.9), 1.0, fade * 0.85);
  albedo = mix(albedo, 0.85, fade * 0.6);
  gl_FragColor = vec4(vLight * albedo * shade * uTint, 1.0);
  #include <colorspace_fragment>
}`;

/** Текстура Three.js з шару: R — альбедо, G/B — нахили на схід і північ (0,5 — рівно). */
export function layerTexture(THREE, layer) {
  const { size, albedo, gx, gy } = layer;
  const data = new Uint8Array(size * size * 4);
  for (let i = 0; i < albedo.length; i++) {
    data[i * 4] = Math.round(albedo[i] * 255);
    data[i * 4 + 1] = Math.round((gx[i] * 0.5 + 0.5) * 255);
    data[i * 4 + 2] = Math.round((gy[i] * 0.5 + 0.5) * 255);
    data[i * 4 + 3] = 255;
  }
  const tex = new THREE.DataTexture(data, size, size, THREE.RGBAFormat);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.magFilter = THREE.LinearFilter;
  tex.minFilter = THREE.LinearMipmapLinearFilter;
  tex.generateMipmaps = true;
  tex.colorSpace = THREE.NoColorSpace;
  tex.anisotropy = 8;
  tex.needsUpdate = true;
  return tex;
}

/** Матеріал ґрунту: sun — спільний Vector3 напряму на Сонце (оновлюється зовні), unit — метрів у одиниці сцени. */
export function createGroundMaterial(THREE, { sun, tint = [1, 1, 1], unit = 1, textures = null } = {}) {
  const tex = textures ?? GROUND_LAYERS.map((spec) => layerTexture(THREE, regolithLayer(spec)));
  return new THREE.ShaderMaterial({
    vertexShader: GROUND_VERT, fragmentShader: GROUND_FRAG, side: THREE.DoubleSide,
    uniforms: {
      uT0: { value: tex[0] }, uT1: { value: tex[1] }, uT2: { value: tex[2] },
      uTile: { value: new THREE.Vector3(...GROUND_LAYERS.map((l) => l.tileM)) }, uNear: { value: NEAR_TILE_M },
      uSun: { value: sun }, uTint: { value: new THREE.Vector3(...tint) }, uUnit: { value: unit },
    },
  });
}
