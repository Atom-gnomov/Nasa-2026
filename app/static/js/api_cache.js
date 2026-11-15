// Спільна пам'ять відповідей API між вкладками (правило «не рахувати одне двічі», рішення власника 2026-11-15):
// 1) та сама деталь у межах сторінки — один запит (одночасні однакові запити зливаються, готові — з пам'яті);
// 2) та сама деталь на іншій вкладці — береться з раннього розрахунку (sessionStorage, ~10 хв).
// Кешуються лише детерміновані GET до розрахункових ендпоінтів; POST, `/api/data/*` і все інше йдуть як є.
export const TTL_MS = 10 * 60 * 1000;
export const MAX_STORED_BYTES = 400_000;
const STORAGE_PREFIX = "lse-api:";
const CACHEABLE = /^\/api\/(timeline|horizon|elevation|metrics|temperature|terrain|events|orbits|system|scene|sites|launch-sites|launch-systems|dsn|meta|compare|models|launch-window)(\/[^?]*)?$/;

// Ключ кешу: шлях + відсортовані параметри; null — не кешуємо.
export function cacheKey(method, input, base = "http://localhost") {
  if ((method ?? "GET").toUpperCase() !== "GET") return null;
  let url;
  try { url = new URL(typeof input === "string" ? input : input?.url ?? String(input), base); } catch { return null; }
  if (!CACHEABLE.test(url.pathname)) return null;
  const params = [...url.searchParams.entries()].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  return `${url.pathname}?${params.map(([k, v]) => `${k}=${v}`).join("&")}`;
}

// Обгортка fetch: повертає функцію з тим самим інтерфейсом. storage — sessionStorage (або null), now — годинник (тести).
export function withCache(realFetch, { storage = null, now = () => Date.now() } = {}) {
  const memory = new Map(); // key → { t, status, body, headers }
  const inflight = new Map(); // key → Promise<entry>
  const stats = { hits: 0, shared: 0, stored: 0, network: 0 };

  const fromStorage = (key) => {
    try {
      const raw = storage?.getItem(STORAGE_PREFIX + key);
      if (!raw) return null;
      const e = JSON.parse(raw);
      return e && now() - e.t < TTL_MS ? e : null;
    } catch { return null; }
  };
  const toStorage = (key, e) => {
    try { if (e.body.length <= MAX_STORED_BYTES) storage?.setItem(STORAGE_PREFIX + key, JSON.stringify(e)); } catch { /* квота — не критично */ }
  };
  const respond = (e) => new Response(e.body, { status: e.status, headers: e.headers });

  async function cached(input, init) {
    const key = cacheKey(init?.method ?? input?.method, input);
    if (!key) return realFetch(input, init);
    let entry = memory.get(key);
    if (entry && now() - entry.t >= TTL_MS) { memory.delete(key); entry = null; }
    if (!entry) { entry = fromStorage(key); if (entry) { memory.set(key, entry); stats.stored += 1; } }
    if (entry) { stats.hits += 1; return respond(entry); }
    let pending = inflight.get(key);
    if (pending) stats.shared += 1;
    else {
      stats.network += 1;
      // Спільний запит не слухає AbortSignal окремого викликача: інакше скасування одного обірве всіх
      pending = realFetch(input, { ...init, signal: undefined }).then(async (res) => {
        const body = await res.text();
        const e = { t: now(), status: res.status, body, headers: { "Content-Type": res.headers.get("Content-Type") ?? "application/json" } };
        if (res.ok) { memory.set(key, e); toStorage(key, e); }
        return e;
      }).finally(() => inflight.delete(key));
      inflight.set(key, pending);
    }
    const signal = init?.signal;
    if (!signal) return respond(await pending);
    if (signal.aborted) throw new DOMException("Aborted", "AbortError");
    return new Promise((resolve, reject) => {
      signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
      pending.then((e) => resolve(respond(e)), reject);
    });
  }
  cached.stats = stats;
  cached.clear = () => { memory.clear(); };
  return cached;
}

export function install() {
  if (typeof window === "undefined" || window.__lseApiCache) return;
  let storage = null;
  try { storage = window.sessionStorage; } catch { /* приватний режим */ }
  window.fetch = withCache(window.fetch.bind(window), { storage });
  window.__lseApiCache = true;
}
install();
