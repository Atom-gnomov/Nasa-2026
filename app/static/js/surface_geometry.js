// Геометрія виду «з поверхні» (G7) без залежностей — спільна для 3D і розгортки, тестується в Node.
// Азимут — від півночі за годинниковою стрілкою, кут місця — від математичного горизонту (docs/MATH.md, §5);
// на полюсі «північ» = напрямок на меридіан 0° (grid north).
// Сцена Three.js: y — угору (зеніт), −z — північ, +x — схід.

const DEG = Math.PI / 180;

// Кутовий діаметр тіла радіуса r на відстані d (той самий кілометр в обох).
export const angularDiameterDeg = (r, d) => (2 * Math.atan(r / d)) / DEG;
// Сонце: R = 695 700 км (IAU 2015, номінальний), 1 а.о. = 149 597 870,7 км (IAU 2012) → ≈ 0,533°.
export const SUN_DIAMETER_DEG = angularDiameterDeg(695_700, 149_597_870.7);
// Земля з Місяця: R = 6378,137 км (WGS 84), велика піввісь орбіти Місяця 384 400 км (NASA Moon Fact Sheet:
// 0,3844·10⁶ км) → ≈ 1,90°; справжній розмір коливається з відстанню (перигей–апогей) приблизно на ±6 %.
export const EARTH_DIAMETER_DEG = angularDiameterDeg(6378.137, 384_400);

// Одиничний вектор напрямку (азимут, кут місця) у координатах сцени.
export function skyVector(azDeg, elDeg) {
  const az = azDeg * DEG, el = elDeg * DEG;
  return [Math.cos(el) * Math.sin(az), Math.sin(el), -Math.cos(el) * Math.cos(az)];
}

// Зворотне: вектор сцени → { az 0…360, el −90…90 }.
export function vectorToAzEl([x, y, z]) {
  const r = Math.hypot(x, y, z) || 1;
  return { az: ((Math.atan2(x, -z) / DEG) + 360) % 360, el: Math.asin(Math.max(-1, Math.min(1, y / r))) / DEG };
}

// Маска /api/horizon → замкнений профіль: азимути 0…360 (останній = перший) і кути рельєфу.
export function horizonProfile(mask) {
  const step = mask.azimuth_step_deg;
  const el = mask.elevations_deg;
  return {
    az: [...el.map((_, i) => i * step), 360],
    el: [...el, el[0]],
  };
}

// Кут рельєфу маски на довільному азимуті (лінійно між сусідніми азимутами маски).
export function maskAt(mask, azDeg) {
  const n = mask.elevations_deg.length;
  const f = ((((azDeg % 360) + 360) % 360) / mask.azimuth_step_deg);
  const i = Math.floor(f) % n, j = (i + 1) % n, t = f - Math.floor(f);
  return mask.elevations_deg[i] * (1 - t) + mask.elevations_deg[j] * t;
}

// Відрізки шляху для розгортки: розрив там, де азимут перескакує через 0°/360°.
export function splitAtWrap(az) {
  const out = [];
  let start = 0;
  for (let i = 1; i < az.length; i++) {
    if (Math.abs(az[i] - az[i - 1]) > 180) { out.push([start, i]); start = i; }
  }
  if (az.length) out.push([start, az.length]);
  return out;
}

// Скільки кроків від i до першої зміни стану (видно ↔ не видно); null, якщо в ряді зміни немає.
export function stepsToChange(flags, i) {
  for (let k = i + 1; k < flags.length; k++) if (flags[k] !== flags[i]) return k - i;
  return null;
}

// Підпис події для тіла в момент i: «до заходу Сонця 12.0 год» / «до сходу Землі 3.5 доби» / «… немає до кінця періоду».
export function eventText(name, visible, i, stepH) {
  const up = visible[i];
  const k = stepsToChange(visible, i);
  const what = `до ${up ? "заходу" : "сходу"} ${name}`;
  if (k === null) return `${up ? "над" : "під"} горизонтом, ${what} — немає до кінця періоду`;
  const h = k * stepH;
  return `${up ? "над" : "під"} горизонтом, ${what} ${h >= 48 ? `${(h / 24).toFixed(1)} доби` : `${h.toFixed(1)} год`}`;
}

// Межі осі кутів місця для розгортки: від −5° (або нижче рельєфу) до найвищої точки з запасом, ≤ 90°.
export function panoramaRange(mask, series) {
  const vals = [...mask.elevations_deg, ...series.sun, ...series.earth];
  const lo = Math.min(-5, ...vals.filter((v) => v > -30));
  const hi = Math.max(10, ...vals);
  const step = hi - lo > 60 ? 30 : hi - lo > 20 ? 10 : 5;
  return { min: Math.floor(lo / step) * step, max: Math.min(90, Math.ceil(hi / step) * step), step };
}

// Підписи сторін світу на горизонті; на самому полюсі — від меридіана 0°.
export function compassLabels(lat) {
  if (Math.abs(lat) > 89.999) {
    return [0, 90, 180, 270].map((az) => ({ az, text: `${az}° від мерид. 0°` }));
  }
  return ["Пн", "Пн-Сх", "Сх", "Пд-Сх", "Пд", "Пд-Зх", "Зх", "Пн-Зх"].map((text, k) => ({ az: k * 45, text }));
}
