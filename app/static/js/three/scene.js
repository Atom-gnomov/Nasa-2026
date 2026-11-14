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
export function createScene(host, { background = 0x000000, logarithmicDepthBuffer = false, quality = qualitySettings() } = {}) {
  if (!hasWebGL()) {
    host.innerHTML = `<p class="placeholder">${NO_WEBGL_MESSAGE}</p>`;
    return null;
  }
  host.innerHTML = "";
  const renderer = new THREE.WebGLRenderer({ antialias: quality.antialias, logarithmicDepthBuffer });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, quality.pixelRatioMax));
  host.append(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(background);
  const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1000);
  camera.position.set(0, 0, 3);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;

  const resize = () => {
    const { clientWidth: w, clientHeight: h } = host;
    renderer.setSize(w, h);
    camera.aspect = w / Math.max(h, 1);
    camera.updateProjectionMatrix();
  };
  const observer = new ResizeObserver(resize);
  observer.observe(host);
  resize();

  renderer.setAnimationLoop(() => {
    controls.update();
    renderer.render(scene, camera);
  });

  const dispose = () => {
    renderer.setAnimationLoop(null);
    observer.disconnect();
    controls.dispose();
    renderer.dispose();
  };
  return { THREE, scene, camera, renderer, controls, dispose };
}
