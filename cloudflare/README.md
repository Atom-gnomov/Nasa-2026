# Деплой на Cloudflare Containers

Worker (`src/index.js`) проксіює запити в контейнер, зібраний із кореневого `Dockerfile`. Потрібен план Workers Paid.

## Через Cloudflare Builds (підключений GitHub)
У налаштуваннях проєкту (Workers → Create → Import repository):
- **Root directory:** `cloudflare`
- **Build command:** `npm install`
- **Deploy command:** `npx wrangler deploy`

## Локально
```bash
cd cloudflare
npm install
npx wrangler login
npx wrangler deploy
```
Потрібен запущений Docker. Після деплою: `npx wrangler containers list`.

## Обмеження
- Диск контейнера тимчасовий. Після засинання (`sleepAfter`, 30 хв без запитів) паки `temperature` і `system` (≈ 84 МБ) завантажуються з Release `data-v1` знову, тому перший запит після паузи повільний.
- Тип `standard-1`: 4 ГіБ пам'яті, 8 ГБ диска. Змінюється в `wrangler.jsonc` (`instance_type`).
- Ціни й версії залежностей перевірте на developers.cloudflare.com/containers.
