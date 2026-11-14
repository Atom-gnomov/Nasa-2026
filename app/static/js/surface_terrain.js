// Поверхня довкола точки для виду «з поверхні» (G7): сітка висот з /api/terrain, освітлення Сонцем,
// геометричні тіні за DEM, фаза Землі та растеризація панорами. Без DOM і WebGL — тестується в Node.
//
// Геометрія. Сітка — у місцевих осях точки: x = схід, y = північ (на полюсі — напрямок на меридіан lon,
// MATH §5), z = вгору. Вузол (e, n) — точка дотичної площини, спроєктована на сферу R = 1737,4 км по радіусу,
// тож положення вузла відносно центра Місяця = (R + h)·(e, n, R)/√(e² + n² + R²), де h — висота вузла відносно
// висоти точки. Так кривина враховується точно: за 5 км поверхня «опускається» на 7 м, за 60 км — на 1 км.
import { skyVector, maskAt } from "./surface_geometry.js";

export const R_MOON_M = 1_737_400;
const DEG = Math.PI / 180;

// ---------- Сітка ----------
export function decodeHeights(b64, n) {
  const bin = atob(b64);
  if (bin.length !== n * n * 4) throw new Error(`Сітка ${n}×${n}: очікується ${n * n * 4} байт, є ${bin.length}`);
  const dv = new DataView(new ArrayBuffer(bin.length));
  for (let i = 0; i < bin.length; i++) dv.setUint8(i, bin.charCodeAt(i));
  const out = new Float32Array(n * n);
  for (let i = 0; i < out.length; i++) out[i] = dv.getFloat32(4 * i, true); // little-endian, як у контракті
  return out;
}

// Відповідь /api/terrain → ділянка з усім, що потрібно для промальовки.
export function makePatch(api) {
  const n = api.n;
  const h = decodeHeights(api.heights_b64, n);
  let hmin = Infinity, hmax = -Infinity;
  for (const v of h) { if (v < hmin) hmin = v; if (v > hmax) hmax = v; }
  const s = api.spacing_m, c = (n - 1) / 2;
  return { n, s, c, half: c * s, h, hmin, hmax, api };
}

// Білінійна висота в точці (схід e, північ nn), м від центра; NaN поза ділянкою.
export function heightAt(p, e, nn) {
  const x = p.c + e / p.s, y = p.c + nn / p.s;
  if (!(x >= 0 && y >= 0 && x <= p.n - 1 && y <= p.n - 1)) return NaN;
  const n = p.n;
  const j = Math.min(n - 2, Math.floor(x)), i = Math.min(n - 2, Math.floor(y));
  const fx = x - j, fy = y - i, k = i * n + j, h = p.h;
  return (h[k] * (1 - fx) + h[k + 1] * fx) * (1 - fy) + (h[k + n] * (1 - fx) + h[k + n + 1] * fx) * fy;
}

// Відстані променя (м): частота — 3,4 % відстані, але не рідше за крок сітки, тож гострі хребти не губляться.
export function terrainSteps(p) {
  if (p.steps) return p.steps;
  const dmax = p.half * 0.98; // вписане коло: кути квадрата не беремо
  const d = [];
  for (let x = 3; x < dmax; x += Math.min(p.s, x * 0.034)) d.push(x);
  d.push(dmax);
  const dist = Float64Array.from(d);
  const sinD = dist.map((x) => x / Math.hypot(x, R_MOON_M));
  const cosD = dist.map((x) => R_MOON_M / Math.hypot(x, R_MOON_M));
  p.steps = { dist, sinD, cosD };
  return p.steps;
}

// ---------- Освітлення Сонцем ----------
// Повертає коефіцієнти 0…1 для кожного вузла: закон Ламберта за нормаллю з DEM і місцевою вертикаллю
// (кривина враховується) × геометрична тінь (промінь до Сонця по DEM, крок < кроку сітки). Далі за межі
// ділянки промінь вважається вільним: тінь від гір поза ділянкою не враховується.
export function lightGrid(p, sunAz, sunEl, { shadows = true, stride = 1, maxSteps = 600 } = {}) {
  const { n, s, h } = p;
  const out = new Float32Array(n * n);
  if (sunEl < -30) return out;
  const sv = skyVector(sunAz, sunEl); // [схід, вгору, −північ] у сцені → переводимо у (схід, північ, вгору)
  const S = [sv[0], -sv[2], sv[1]];
  const R = R_MOON_M;
  const step = Math.max(5, s * 0.6);
  const hmax = p.hmax;

  const lambert = (i, j) => {
    const e = (j - p.c) * s, nn = (i - p.c) * s;
    const rho = Math.hypot(e, nn, R);
    const ux = e / rho, uy = nn / rho, uz = R / rho;
    // місцева вісь «схід»: (1,0,0) мінус складова вздовж вертикалі
    let ex = 1 - ux * ux, ey = -ux * uy, ez = -ux * uz;
    const el = Math.hypot(ex, ey, ez);
    ex /= el; ey /= el; ez /= el;
    const nx = uy * ez - uz * ey, ny = uz * ex - ux * ez, nz = ux * ey - uy * ex; // північ = вертикаль × схід
    const j0 = Math.max(0, j - 1), j1 = Math.min(n - 1, j + 1), i0 = Math.max(0, i - 1), i1 = Math.min(n - 1, i + 1);
    const gx = (h[i * n + j1] - h[i * n + j0]) / ((j1 - j0) * s);
    const gy = (h[i1 * n + j] - h[i0 * n + j]) / ((i1 - i0) * s);
    let vx = -gx * ex - gy * nx + ux, vy = -gx * ey - gy * ny + uy, vz = -gx * ez - gy * nz + uz;
    const vl = Math.hypot(vx, vy, vz);
    vx /= vl; vy /= vl; vz /= vl;
    return Math.max(0, vx * S[0] + vy * S[1] + vz * S[2]);
  };

  const shadowed = (i, j) => {
    const e = (j - p.c) * s, nn = (i - p.c) * s;
    const rho = Math.hypot(e, nn, R);
    const rs = R + h[i * n + j];
    const px = (rs * e) / rho, py = (rs * nn) / rho, pz = (rs * R) / rho;
    for (let k = 1, t = step; k <= maxSteps; k++, t += step) {
      const qx = px + t * S[0], qy = py + t * S[1], qz = pz + t * S[2];
      if (qz <= 0) return false;
      const kk = R / qz;
      const hh = heightAt(p, qx * kk, qy * kk);
      if (Number.isNaN(hh)) return false;
      const rq = Math.sqrt(qx * qx + qy * qy + qz * qz);
      if (rq < R + hh - 0.05) return true;
      if (rq > R + hmax + 1) return false;
    }
    return false;
  };

  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) out[i * n + j] = lambert(i, j);
  }
  if (!shadows) return out;
  const half = (stride - 1) / 2;
  for (let i0 = 0; i0 < n; i0 += stride) {
    for (let j0 = 0; j0 < n; j0 += stride) {
      const ic = Math.min(n - 1, Math.round(i0 + half)), jc = Math.min(n - 1, Math.round(j0 + half));
      if (!(out[ic * n + jc] > 0) && stride === 1) continue;
      if (!shadowed(ic, jc)) continue;
      for (let i = i0; i < Math.min(n, i0 + stride); i++) for (let j = j0; j < Math.min(n, j0 + stride); j++) out[i * n + j] = 0;
    }
  }
  return out;
}

// Умовне заповнення тіней: cos(кут схилу) за DEM — крутіші схили темніші, тож форма рельєфу читається й без Сонця.
// Лише візуальна підказка (див. прапорець «Підсвітка тіней»); фізичного освітлення воно не описує.
export function slopeFill(p) {
  if (p.fill) return p.fill;
  const { n, s, h } = p;
  const out = new Float32Array(n * n);
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      const j0 = Math.max(0, j - 1), j1 = Math.min(n - 1, j + 1), i0 = Math.max(0, i - 1), i1 = Math.min(n - 1, i + 1);
      const gx = (h[i * n + j1] - h[i * n + j0]) / ((j1 - j0) * s);
      const gy = (h[i1 * n + j] - h[i0 * n + j]) / ((i1 - i0) * s);
      out[i * n + j] = 1 / Math.sqrt(1 + gx * gx + gy * gy);
    }
  }
  p.fill = out;
  return out;
}

// ---------- Фаза Землі ----------
// Освітлена частка диска Землі з поверхні Місяця: (1 − cos ε)/2, де ε — кутова відстань Сонця від Землі
// на небі місця (Сонце далеко: поправка на кут при Землі ≤ 0,26°). Землі «повня» (ε = 180°) — коли на Землі
// новий Місяць. bearing — напрямок на Сонце від Землі на небі, градуси за годинниковою від «вгору».
export function earthPhase(sunAz, sunEl, earthAz, earthEl) {
  const a = skyVector(sunAz, sunEl), b = skyVector(earthAz, earthEl);
  const cosEps = Math.max(-1, Math.min(1, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]));
  const dl = (sunAz - earthAz) * DEG, f1 = earthEl * DEG, f2 = sunEl * DEG;
  const bearing = (Math.atan2(Math.sin(dl) * Math.cos(f2), Math.cos(f1) * Math.sin(f2) - Math.sin(f1) * Math.cos(f2) * Math.cos(dl)) / DEG + 360) % 360;
  return { fraction: (1 - cosEps) / 2, bearing, elongation: Math.acos(cosEps) / DEG };
}

// ---------- Панорама ----------
// Яскравість пікселя: ambient (земне сяйво, умовне) + частка освітлення. Один сірий канал — реголіт без кольору.
export function shadeGray(light, ambient = 0.03, fill = 1) {
  return Math.round(255 * Math.max(0, Math.min(1, ambient * (0.35 + 0.65 * fill) + 0.8 * light)));
}
const rgba = (g) => (0xff000000 | (g << 16) | (g << 8) | g) >>> 0;

// Растеризує поверхню в pixels (Uint32Array width×height, ABGR; небо лишається 0 — прозоре).
// Циліндрична проєкція: x ↔ азимут, y ↔ кут місця, однаковий масштаб градусів (ppd = width / fov).
// Алгоритм «карта висот»: для кожного стовпця промінь іде від близького до далекого; піксель малюється
// лише коли точка поверхні вища за все, що вже намальовано ближче, — кожен піксель пишеться один раз.
export function renderTerrain(p, light, o) {
  const { pixels, width: W, height: H, viewAz, viewEl, fov, eye = 2, exag = 1, mask = null, ambient = 0.03, fill = null, rings = null } = o;
  const ppd = W / fov, cy = H / 2, R = R_MOON_M;
  pixels.fill(0);
  const steps = p ? terrainSteps(p) : null;
  const farGray = rgba(shadeGray(o.farLight ?? 0, ambient));
  let drawn = 0;
  const ringRows = [];
  // кільця дальності: перший намальований піксель після відстані кільця фарбується в колір кільця
  const ringList = rings ? [...rings].sort((a, b) => a - b) : [];
  const RING = rgba(150);
  for (let x = 0; x < W; x++) {
    const az = viewAz + (x + 0.5 - W / 2) / ppd;
    const azr = az * DEG, se = Math.sin(azr), sn = Math.cos(azr);
    let ymin = H, ri = 0, pendingRing = 0;
    if (steps) {
      const { dist, sinD, cosD } = steps;
      for (let k = 0; k < dist.length && ymin > 0; k++) {
        if (ri < ringList.length && dist[k] >= ringList[ri]) {
          pendingRing = ringList[ri];
          while (ri < ringList.length && dist[k] >= ringList[ri]) ri++;
        }
        const e = dist[k] * se, nn = dist[k] * sn;
        const hv = heightAt(p, e, nn);
        if (Number.isNaN(hv)) break;
        const hh = hv * exag;
        const el = Math.atan2((R + hh) * cosD[k] - R - eye, (R + hh) * sinD[k]) / DEG;
        let yi = Math.floor(cy - (el - viewEl) * ppd);
        if (yi < 0) yi = 0;
        if (yi >= ymin) continue;
        const jj = Math.round(p.c + e / p.s), ii = Math.round(p.c + nn / p.s);
        const col = rgba(shadeGray(light ? light[ii * p.n + jj] : 0, ambient, fill ? fill[ii * p.n + jj] : 1));
        for (let y = yi; y < ymin; y++) pixels[y * W + x] = col;
        if (pendingRing) {
          pixels[yi * W + x] = RING;
          if (x === W >> 1) ringRows.push({ d: pendingRing, y: yi });
          pendingRing = 0;
        }
        drawn += ymin - yi;
        ymin = yi;
      }
    }
    // за межами ділянки — силует за маскою горизонту (без деталей і тіней)
    if (mask && ymin > 0) {
      const elM = maskAt(mask, ((az % 360) + 360) % 360);
      let ym = Math.floor(cy - (elM - viewEl) * ppd);
      if (ym < 0) ym = 0;
      for (let y = ym; y < ymin; y++) pixels[y * W + x] = farGray;
      drawn += Math.max(0, ymin - ym);
    } else if (!steps && !mask) {
      // без даних — гладка земля під горизонтом
      for (let y = Math.max(0, Math.floor(cy + viewEl * ppd)); y < H; y++) pixels[y * W + x] = farGray;
    }
  }
  return { drawn, ringRows };
}
