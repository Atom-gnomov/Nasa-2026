# Nasa-2026

NASA Space Apps Challenge 2026 — інструмент для порівняння місць і дат посадки на південному полюсі Місяця
(положення Сонця й Землі над горизонтом, енергія та вікна зв'язку).
Розрахунки й візуалізація — на офіційних даних NASA: рельєф LOLA, температура LRO Diviner, ефемериди JPL DE440,
3D-моделі NASA 3D Resources; ключові значення звірено з JPL Horizons і LROC (docs/MATH.md, §18).

> Актуальна версія теки `docs/` — у гілці [`coordination`](https://github.com/Atom-gnomov/Nasa-2026/tree/coordination/docs); тут — копія на момент останньої синхронізації.

## Що вже є

Вкладки: **Місяць** (глобус, підбір і порівняння місць), **Система** (Земля–Місяць–Сонце, траєкторія перельоту й «Симуляція» польоту з телеметрією), **Місія** (маса, вартість, ризик, ракета), **План місії** (від вимог до місця посадки — до майданчика, ракети, траєкторії й дати старту з автовибором), **Вікно запуску** (шкала дат у %). Є вид «з поверхні», температура й радіація, перемикач UA/EN, наскрізний вибір між вкладками. Повний перелік і що лишається — [docs/TASKS.md](docs/TASKS.md), «Поточний стан».

- [docs/CHALLENGE.md](docs/CHALLENGE.md) — оригінальний текст завдання (англійською)
- [docs/VISION.md](docs/VISION.md) — що хочемо бачити ми і команда (наповнюється поступово)
- [docs/MODULES.md](docs/MODULES.md) — вимоги до модулів і API
- [docs/MATH.md](docs/MATH.md) — математика розрахунків і контрольні числа
- [docs/CONTRACTS.md](docs/CONTRACTS.md) — контракти API, даних і фронтенду (`contracts/openapi.yaml`)
- [docs/RESOURCES.md](docs/RESOURCES.md) — джерела даних, бібліотеки та стек візуалізації
- [docs/TASKS.md](docs/TASKS.md) — задачі, порядок реалізації, розподіл між агентами
- [docs/BOARD.md](docs/BOARD.md) — дошка агентів: хто що робить і що зроблено
- [docs/PROPOSALS.md](docs/PROPOSALS.md) — пропозиції та покращення
- [AGENTS.md](AGENTS.md) — точка входу для агентів (мова роботи — українська)

## Запуск

Потрібен Python 3.11+.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
flask --app app run --debug
```

Сайт відкриється на http://127.0.0.1:5000. Тести: `python -m pytest`.

Залежності включають ефемериди JPL DE440 (пакет `naif-de440`, ~114 МБ). Свій файл ефемерид можна вказати змінною `LSE_EPHEMERIS_PATH`.

### Дані NASA для глобуса, 3D-виду системи й температури

Великі дані в git не зберігаються: їх завантажують і готують скрипти з `tools/` у `data_cache/` (докладно — [tools/README.md](tools/README.md)).

**Застосунок сам готує дані у фоні** (задача I7): під час запуску він перевіряє, чого бракує, і запускає потрібні скрипти.
За замовчуванням готуються температура Diviner (≈ 3,4 ГБ завантаження) і 3D-ресурси системи (≈ 6 МБ); текстури й рельєф
глобуса важчі (≈ 1,3 ГБ і більше), їх вмикають окремо. Сайт працює з тим, що вже є, а зверху показується банер «Готую дані»
з останнім рядком роботи скрипта; після помилки (наприклад, немає мережі) автоповтору немає — кнопка «Спробувати знову»
або перезапуск. Стан також у `GET /api/data/status`, а запуск вручну — `POST /api/data/prepare`.

```bash
curl http://127.0.0.1:5000/api/data/status                       # що готове, що готується, що не вдалося
curl -X POST http://127.0.0.1:5000/api/data/prepare -H "Content-Type: application/json" -d '{"datasets": ["globe"]}'
LSE_AUTO_PREPARE=0 flask --app app:create_app run                # вимкнути автоматичну підготовку
```

Вручну те саме роблять скрипти:

```bash
pip install tifffile imagecodecs Pillow                 # лише для першого скрипта
python tools/build_globe_textures.py --with-ldem64      # LOLA + CGI Moon Kit: ~1,3 ГБ, ~25 хв
python tools/build_system_assets.py                     # NASA 3D Resources: ~6 МБ
python tools/build_temperature_data.py                  # LRO Diviner: ~3,4 ГБ
```

Без цих даних сайт працює, але глобус і 3D-вид показують повідомлення, горизонт рахується як гладка сфера,
а `/api/temperature` відповідає 503 з поясненням: дані готуються, підготовка не вдалась (з причиною) або їх треба запустити.

Приклад запиту метрик для точки біля південного полюса:

```bash
curl "http://127.0.0.1:5000/api/metrics?lat=-89.5&lon=0&datetime=2027-07-01T00:00&height=2"
```

### Хостинг (Docker)

Образ: `Dockerfile` (Python 3.13, gunicorn, не від root). Дані NASA лежать у томі `/data` (`LSE_CACHE_DIR`), тому переживають
перезапуск; при першому старті вони готуються в фоні, поки сайт уже працює.

```bash
docker compose up -d --build          # сайт на http://localhost:8000, дані — у томі lse-data
# або без compose:
docker build -t lunar-mission-builder .
docker run -p 8000:8000 -v lse-data:/data lunar-mission-builder
```

Готовий образ у GitHub Container Registry (збирається workflow `Docker publish`, вручну або тегом `v*`):

```bash
docker run -p 8000:8000 -v lse-data:/data ghcr.io/atom-gnomov/nasa-2026:latest
```

Готові оброблені пакети даних лежать у Release `data-v1` (`temperature-full`, `system-full`, `globe-full`, ≈ 160 МБ разом) і описані в
`app/data/data_packs.json`: першому запуску не треба тягнути ≈ 3,4 ГБ сирих даних — застосунок бере пакети сам
(`LSE_AUTO_PREPARE_MODE=pack`) і перевіряє `sha256`. Пакети збирає й публікує `python tools/build_data_pack.py --publish`.

Ресурси (замірено без даних NASA; з даними +1–2 ГБ оцінка): 2 воркери ≈ 130 МБ пам'яті. Для демо — 1 vCPU, 1–2 ГБ ОЗП, диск 2–3 ГБ
(з готовим пакетом даних) або ≈ 10 ГБ (з сирими даними температури й глобуса). `WEB_CONCURRENCY` — кількість воркерів (типово 2),
`PORT` — порт (типово 8000); перевірка живості — `GET /api/meta`.

Готові конфіги: `fly.toml` (Fly.io: `fly launch --no-deploy --copy-config`, `fly volumes create lse_data --size 5`, `fly deploy`)
і `render.yaml` (Render Blueprint; постійний диск є лише в платному плані). Секрети (`SECRET_KEY`) задавайте змінними середовища
хостингу, не в файлах.

#### Cloudflare

Два способи, залежно від того, що саме потрібно:

1. **Cloudflare Containers** (теки `cloudflare/`): той самий образ працює за Worker-ом на платформі Cloudflare. Потрібен план Workers Paid (від $5/міс).
   ```bash
   cd cloudflare && npm install
   npx wrangler login
   npx wrangler secret put SECRET_KEY
   npx wrangler deploy
   ```
   Диск контейнера **тимчасовий**: після сну (за замовчуванням 30 хв простою) дані NASA готуються заново, тож варто опублікувати пакет даних
   (`LSE_AUTO_PREPARE_MODE=pack`). `instance_type: standard-1` (½ vCPU, 4 ГіБ, 8 ГБ диска) — у `cloudflare/wrangler.jsonc`.
2. **Cloudflare Tunnel** для будь-якої машини з Docker (VPS, свій сервер): без відкритих портів, HTTPS від Cloudflare. Створіть тунель в
   панелі Zero Trust, додайте `TUNNEL_TOKEN=…` у `.env`, вкажіть публічне ім'я хоста → `http://web:8000` і запустіть
   `docker compose --profile tunnel up -d`.

### Змінні середовища

Задаються змінними середовища або файлом `.env` (він у `.gitignore`; зразок — `.env.example`). Секрети лише тут, не в коді.

| Змінна | За замовчуванням | Що робить |
|---|---|---|
| `LSE_CACHE_DIR` | `data_cache/` | Каталог великих даних (текстури, 3D-ресурси, стан підготовки) |
| `LSE_DEM_DIR` | `<CACHE_DIR>/globe/src` | Рельєф LOLA (PDS `.img` + `.lbl`) |
| `LSE_TEMP_DIR` | `<CACHE_DIR>/temperature` | Температурні дані Diviner |
| `LSE_EPHEMERIS_PATH` | пакет `naif-de440` | Власний файл ефемерид JPL |
| `LSE_MOON_ORIENTATION` | `iau` | Орієнтація Місяця: `iau` (модель IAU 2015) або `pck` (ядра NAIF DE440; `python tools/download_kernels.py`) |
| `LSE_KERNEL_DIR` | `data_cache/kernels` | Каталог ядер NAIF для `LSE_MOON_ORIENTATION=pck` |
| `LSE_AUTO_PREPARE` | `1` | `0` вимикає автоматичну підготовку даних у фоні (CI, автономна робота) |
| `LSE_AUTO_PREPARE_MODE` | `pack` | Як готувати дані: `pack` — готовий пакет із GitHub Release (запасний шлях — збірка зі скриптів), `light` — легкий пакет, `full` — лише збірка з PDS |
| `LSE_AUTO_PREPARE_DATASETS` | `temperature,system` | Які набори готувати самі: `temperature`, `system`, `globe` |
| `SECRET_KEY` | `dev-only-change-me` | Секрет сесій Flask; у продакшні задайте свій |
