// Текстура місячного ґрунту (реголіту) для виду з поверхні: тайлова карта дрібної деталі + колір ґрунту з
// реальної карти Місяця в точці спостереження.
//
// Що тут справжнє, а що ні (чесно):
//   • колір (відтінок) ґрунту береться з текстури CGI Moon Kit (LRO LROC WAC, NASA SVS) у координатах точки —
//     це справжні дані, але їхня роздільність — кілометри на піксель;
//   • дрібна деталь (зерно, дрібні кратери, камені) — процедурна: такої роздільності знімків для точки немає.
//     Вона лише додає видимості рельєфу під низьким Сонцем і не є знімком конкретного місця.
// Освітлення й тіні — не тут: їх дає lightGrid (DEM LOLA, справжнє положення Сонця); текстура їх лише множить.

export const TEXTURE_SIZE = 256;
export const TILE_METERS = 96; // розмір однієї плитки текстури на ґрунті, м

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

// Періодичний шум значень: решітка period×period випадкових чисел, білінійно з плавною кривою; стик країв точний.
function valueNoise(size, period, rand) {
  const grid = Float32Array.from({ length: period * period }, () => rand());
  const out = new Float32Array(size * size);
  for (let y = 0; y < size; y++) {
    const fy = (y / size) * period, y0 = Math.floor(fy), ty = smooth(fy - y0);
    for (let x = 0; x < size; x++) {
      const fx = (x / size) * period, x0 = Math.floor(fx), tx = smooth(fx - x0);
      const g = (i, j) => grid[(((j % period) + period) % period) * period + (((i % period) + period) % period)];
      const a = g(x0, y0) + (g(x0 + 1, y0) - g(x0, y0)) * tx;
      const b = g(x0, y0 + 1) + (g(x0 + 1, y0 + 1) - g(x0, y0 + 1)) * tx;
      out[y * size + x] = a + (b - a) * ty;
    }
  }
  return out;
}

/**
 * Тайлова карта яскравості реголіту, значення 0.55…1.0 (множник до освітленості).
 * Шари: фрактальний шум (хвилі й зерно), дрібні кратери з піднятими краями, випадкові камінці.
 * Краї замкнені (індекси за модулем), тож плитки стикуються без швів.
 */
export function regolithMap(size = TEXTURE_SIZE, seed = 20241114) {
  const rand = rng(seed);
  const out = new Float32Array(size * size);
  const octaves = [[4, 0.34], [8, 0.26], [16, 0.20], [32, 0.14], [64, 0.06]];
  for (const [period, weight] of octaves) {
    const n = valueNoise(size, period, rand);
    for (let i = 0; i < out.length; i++) out[i] += n[i] * weight;
  }
  const wrap = (v) => ((v % size) + size) % size;
  const stamp = (cx, cy, r, depth, rim) => { // кратер: затемнена чаша й світліший вал
    const R = Math.ceil(r * 1.5);
    for (let dy = -R; dy <= R; dy++) {
      for (let dx = -R; dx <= R; dx++) {
        const d = Math.hypot(dx, dy) / r;
        let k = 0;
        if (d < 1) k = -depth * (1 - d * d);
        else if (d < 1.35) k = rim * (1 - (d - 1) / 0.35);
        if (k) out[wrap(cy + dy) * size + wrap(cx + dx)] += k;
      }
    }
  };
  for (let i = 0; i < 26; i++) stamp(Math.floor(rand() * size), Math.floor(rand() * size), 3 + rand() * 10, 0.16 + rand() * 0.12, 0.07);
  for (let i = 0; i < 90; i++) { // камінці: дрібні світлі цятки
    const x = Math.floor(rand() * size), y = Math.floor(rand() * size);
    out[wrap(y) * size + wrap(x)] += 0.22 * rand();
    out[wrap(y) * size + wrap(x + 1)] += 0.10 * rand();
  }
  let lo = Infinity, hi = -Infinity;
  for (const v of out) { if (v < lo) lo = v; if (v > hi) hi = v; }
  const span = hi - lo || 1;
  for (let i = 0; i < out.length; i++) out[i] = 0.55 + 0.45 * ((out[i] - lo) / span);
  return out;
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

/** Текстура Three.js з карти яскравості (RGB — однаковий сірий), повторювана, з мипмапами й анізотропією. */
export function regolithTexture(THREE, renderer = null, size = TEXTURE_SIZE) {
  const m = regolithMap(size);
  const data = new Uint8Array(size * size * 4);
  for (let i = 0; i < m.length; i++) {
    const v = Math.round(255 * m[i]);
    data[i * 4] = data[i * 4 + 1] = data[i * 4 + 2] = v;
    data[i * 4 + 3] = 255;
  }
  const tex = new THREE.DataTexture(data, size, size, THREE.RGBAFormat);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.magFilter = THREE.LinearFilter;
  tex.minFilter = THREE.LinearMipmapLinearFilter;
  tex.generateMipmaps = true;
  tex.colorSpace = THREE.NoColorSpace;
  if (renderer) tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
  tex.needsUpdate = true;
  return tex;
}
