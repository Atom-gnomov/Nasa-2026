// Місяць-тло: на сторінках кроків планування (Місія, Підбір, План, Узгодженість, Звіт) — проста модель Місяця, що повільно
// обертається на задньому плані, як у вкладці «Місяць». Текстура — data_cache/globe/color.jpg; немає текстури чи WebGL — тла немає.
const PAGES = ["page-mission", "page-search", "page-plan", "page-consistency", "page-report"];
const SPIN_RAD_PER_S = 0.025;

// Чи показувати Місяць-тло на сторінці з такими класами body.
export const wantsBackdrop = (bodyClass) => PAGES.some((p) => String(bodyClass ?? "").split(/\s+/).includes(p));

async function start() {
  const THREE = await import("three");
  const info = await fetch("/assets/globe/globe.json", { cache: "no-cache" }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  const file = info?.color?.file;
  if (!file) return;

  const canvas = document.createElement("canvas");
  canvas.id = "moon-backdrop";
  canvas.setAttribute("aria-hidden", "true");
  document.body.prepend(canvas);
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 100);
  camera.position.set(0, 0, 24);
  scene.add(new THREE.AmbientLight(0xffffff, 0.35));
  const sun = new THREE.DirectionalLight(0xffffff, 2.6);
  sun.position.set(-6, 3, 5);
  scene.add(sun);

  const texture = await new THREE.TextureLoader().loadAsync(`/assets/globe/${file}?v=${info.version ?? 0}`);
  texture.colorSpace = THREE.SRGBColorSpace;
  const moon = new THREE.Mesh(new THREE.SphereGeometry(3, 96, 64), new THREE.MeshStandardMaterial({ map: texture, roughness: 1, metalness: 0 }));
  moon.rotation.set(0.12, 0, 0.1);
  scene.add(moon);

  const resize = () => {
    const w = window.innerWidth, h = window.innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    // Місяць висить справа внизу, частково за краєм кадру
    camera.setViewOffset(w, h, -w * 0.30, -h * 0.14, w, h);
    camera.updateProjectionMatrix();
  };
  resize();
  window.addEventListener("resize", resize);

  const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let last = performance.now();
  const frame = (now) => {
    if (!document.hidden && !still) moon.rotation.y += ((now - last) / 1000) * SPIN_RAD_PER_S;
    last = now;
    renderer.render(scene, camera);
    if (!still) requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
  document.body.classList.add("has-moon-backdrop");
}

if (typeof document !== "undefined" && wantsBackdrop(document.body.className)) {
  const run = () => start().catch((err) => console.warn("moon-backdrop:", err));
  if (document.readyState === "complete") run(); else window.addEventListener("load", run, { once: true });
}
