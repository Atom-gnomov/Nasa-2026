// М16. Режими якості 3D: «низька» (за замовчуванням, VISION — щоб працювало на слабкому ноутбуці) і «висока».
// Вибір — властивість пристрою, а не стану сцени: зберігається в localStorage і не потрапляє в посилання.
// Діагностика: ?webgl=0 в адресі вмикає 2D-заглушку так, ніби браузер не підтримує WebGL.

const KEY = "lse-quality";

export const QUALITY = {
  low: {
    label: "низька",
    pixelRatioMax: 1, // без надвибірки на екранах з високою щільністю
    antialias: false,
    anisotropyMax: 4,
    polarTiles: false, // детальний рельєф полюса LOLA 80 і 20 м (≈ 60 МБ) не вантажимо
  },
  high: {
    label: "висока",
    pixelRatioMax: 2,
    antialias: true,
    anisotropyMax: 16,
    polarTiles: true,
  },
};
export const DEFAULT_QUALITY = "low";

const valid = (q) => typeof q === "string" && Object.hasOwn(QUALITY, q);

export function getQuality(storage = globalThis.localStorage) {
  try {
    const q = storage?.getItem(KEY);
    return valid(q) ? q : DEFAULT_QUALITY;
  } catch {
    return DEFAULT_QUALITY; // приватний режим
  }
}

export function setQuality(q, storage = globalThis.localStorage) {
  if (!valid(q)) return false;
  try { storage?.setItem(KEY, q); } catch { /* приватний режим — діє до перезавантаження */ }
  return true;
}

export function qualitySettings(q = getQuality()) {
  return QUALITY[valid(q) ? q : DEFAULT_QUALITY];
}

export function webglDisabledByUrl(search = globalThis.location?.search ?? "") {
  return new URLSearchParams(search).get("webgl") === "0";
}

// Підключає <select> вибору якості; зміна перезавантажує сторінку, бо згладжування й набір текстур
// задаються при створенні сцени.
export function mountQualitySelect(select, { reload = () => globalThis.location.reload() } = {}) {
  if (!select) return;
  select.replaceChildren(...Object.entries(QUALITY).map(([value, { label }]) => new Option(label, value)));
  select.value = getQuality();
  select.addEventListener("change", () => {
    if (setQuality(select.value)) reload();
  });
}
