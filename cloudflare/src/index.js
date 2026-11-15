import { Container, getContainer } from "@cloudflare/containers";

// Один контейнер на весь сайт: Flask-застосунок із gunicorn на порту 8000.
// Диск контейнера тимчасовий: після засинання дані (паки з Release data-v1) завантажуються знову.
export class LunarApp extends Container {
  defaultPort = 8000;
  sleepAfter = "30m";
  envVars = {
    PORT: "8000",
    WEB_CONCURRENCY: "2",
    LSE_CACHE_DIR: "/data",
    LSE_AUTO_PREPARE_MODE: "pack",
    LSE_AUTO_PREPARE_DATASETS: "temperature,system",
  };
}

export default {
  async fetch(request, env) {
    return getContainer(env.LUNAR_APP).fetch(request);
  },
};
