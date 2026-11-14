// М16. 3D-підсистема: спільна основа для всіх 3D-сцен (глобус Місяця, 3D-вид системи).
// Three.js підключено через importmap у base.html.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { qualitySettings, webglDisabledByUrl } from "./quality.js";

export function hasWebGL() {
  if (webglDisabledByUrl()) return false;
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2"));
  } catch {
    return false;
  }
}

// Перетворення селенографічних координат у точку на сфері (Y — до північного полюса).
export function latLonToVector3(lat, lon, radius = 1) {
  const phi = THREE.MathUtils.degToRad(90 - lat);
  const theta = THREE.MathUtils.degToRad(lon);
  return new THREE.Vector3(
    radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    -radius * Math.sin(phi) * Math.sin(theta),
  );
}

export function vector3ToLatLon(v) {
  const r = v.length();
  const lat = 90 - THREE.MathUtils.radToDeg(Math.acos(v.y / r));
  const lon = THREE.MathUtils.radToDeg(Math.atan2(-v.z, v.x));
  return { lat, lon };
}

export const NO_WEBGL_MESSAGE = "3D недоступне: браузер не підтримує WebGL 2.";

// Анізотропна фільтрація текстур у межах режиму якості.
export function anisotropy(renderer, quality = qualitySettings()) {
  return Math.min(renderer.capabilities.getMaxAnisotropy(), quality.anisotropyMax);
}

// Створює сцену в контейнері host. Повертає об'єкти сцени та dispose().
// logarithmicDepthBuffer — для сцен із відстанями, що різняться в мільйони разів (система Сонце–Земля–Місяць).
// Згладжування й щільність пікселів — з режиму якості (three/quality.js).
// fade: false — полотно лишається прозорим, доки код сцени не викличе reveal() (коли в кадрі вже є що показати).
export function createScene(host, { background = null, logarithmicDepthBuffer = false, quality = qualitySettings(), fade = true } = {}) {
  if (!hasWebGL()) {
    host.innerHTML = `<p class="placeholder">${NO_WEBGL_MESSAGE}</p>`;
    return null;
  }
  host.innerHTML = "";
  const renderer = new THREE.WebGLRenderer({ antialias: quality.antialias, logarithmicDepthBuffer, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, quality.pixelRatioMax));
  host.append(renderer.domElement);
  // Планета проявляється плавно, а не виринає, коли завершиться завантаження текстур
  renderer.domElement.style.opacity = "0";
  renderer.domElement.style.transition = "opacity .7s ease";
  const reveal = () => requestAnimationFrame(() => requestAnimationFrame(() => { renderer.domElement.style.opacity = "1"; }));
  if (fade) reveal();

  const scene = new THREE.Scene();
  // Прозорий фон за замовчуванням: крізь canvas видно зоряне тло сторінки (css/cosmos.css).
  renderer.setClearColor(0x000000, 0);
  scene.background = background === null ? null : new THREE.Color(background);
  const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1000);
  camera.position.set(0, 0, 3);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;

  // Сцена на весь екран позаду віджетів; центр кадру зсувається у вільну між панелями ділянку (вид не ховається під панелями).
  const stageShift = () => {
    const cs = getComputedStyle(document.body);
    if (!/page-(moon|system)/.test(document.body.className)) return [0, 0];
    const left = parseFloat(cs.getPropertyValue("--scene-left")) || 0;
    const right = parseFloat(cs.getPropertyValue("--scene-right")) || 0;
    const top = parseFloat(cs.getPropertyValue("--header-h")) || 0;
    const r = host.getBoundingClientRect();
    const dx = (left + window.innerWidth - right) / 2 - (r.left + r.width / 2);
    const dy = (top + window.innerHeight) / 2 - (r.top + r.height / 2);
    return [Math.round(dx), Math.round(dy)];
  };
  let lastKey = "";
  const resize = () => {
    const { clientWidth: w, clientHeight: h } = host;
    const [dx, dy] = w > 0 && h > 0 ? stageShift() : [0, 0];
    const key = `${w}x${h}`;
    const full = `${key}|${dx}|${dy}`;
    if (full === lastKey) return; // нічого не змінилось: не перевиділяємо буфер полотна (це гальмує й блимає)
    if (!lastKey.startsWith(key + "|")) renderer.setSize(w, h);
    lastKey = full;
    camera.aspect = w / Math.max(h, 1);
    if (dx || dy) camera.setViewOffset(w, h, -dx, -dy, w, h);
    else camera.clearViewOffset();
    camera.updateProjectionMatrix();
  };
  const observer = new ResizeObserver(resize);
  observer.observe(host);
  // --scene-left/right задає workspace_ui.js через style на <body>: слідкуємо за ним
  const styleWatch = new MutationObserver(resize);
  styleWatch.observe(document.body, { attributes: true, attributeFilter: ["style", "data-expanded", "class"] });
  window.addEventListener("resize", resize);
  resize();

  const shown = () => (typeof host.checkVisibility === "function" ? host.checkVisibility({ visibilityProperty: true }) : true);
  renderer.setAnimationLoop(() => {
    controls.update();
    if (shown()) renderer.render(scene, camera); // прихована сцена (інший режим) не навантажує відеокарту
  });

  const dispose = () => {
    renderer.setAnimationLoop(null);
    observer.disconnect();
    styleWatch.disconnect();
    window.removeEventListener("resize", resize);
    controls.dispose();
    renderer.dispose();
  };
  return { THREE, scene, camera, renderer, controls, dispose, reveal };
}
