// Worker пропускає запити до контейнера із застосунком (образ із кореня репозиторію, gunicorn на порту 8000).
// Контейнер засинає після простою й прокидається на наступний запит (перший запит після сну — повільніший).
import { Container, getContainer } from "@cloudflare/containers";

export class LunarMissionBuilder extends Container {
  defaultPort = 8000;
  sleepAfter = "30m";
  // Диск контейнера тимчасовий: дані NASA готуються після кожного холодного старту (LSE_AUTO_PREPARE_MODE=pack — швидко,
  // якщо опубліковано пакет даних, I10). Без даних сайт працює на гладкій сфері.
  envVars = {
    PORT: "8000",
    WEB_CONCURRENCY: "2",
    LSE_CACHE_DIR: "/data",
    LSE_AUTO_PREPARE: "1",
    LSE_AUTO_PREPARE_MODE: "pack",
    LSE_AUTO_PREPARE_DATASETS: "temperature,system",
    // SECRET_KEY задайте секретом: npx wrangler secret put SECRET_KEY (у коді його немає)
  };
}

export default {
  async fetch(request, env) {
    // Один постійний екземпляр: кеші в пам'яті (ефемериди, перельоти) і підготовлені дані спільні для всіх запитів
    return getContainer(env.LMB, "main").fetch(request);
  },
};
