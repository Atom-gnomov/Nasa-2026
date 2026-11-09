# Источники для визуализации и расчётов

Стартовая точка для людей и агентов, которые начинают работу над проектом.
Требования к продукту — в [VISION.md](VISION.md), исходное задание — в [CHALLENGE.md](CHALLENGE.md).

> Ссылки собраны 2026-11-09. Перед использованием проверяйте актуальные версии файлов и лицензии.
> Пометка ⚠️ означает, что источник не перепроверен или у него есть известные оговорки.

---

## 1. Текстуры и 3D-модели (вкладки «Луна» и 3D-вид системы)

| Источник | Что даёт | Ссылка |
|---|---|---|
| **NASA SVS — CGI Moon Kit** | Цветная карта Луны (LROC, до 16K) и карта высот LOLA (displacement) для 3D-глобуса. Основной источник текстур для Three.js | https://svs.gsfc.nasa.gov/4720 |
| **NASA Visible Earth — Blue Marble** | Текстуры Земли (день, ночь, облака) для 3D-вида системы | https://visibleearth.nasa.gov/collection/1484/blue-marble |
| **NASA 3D Resources** | Готовые 3D-модели (LRO, посадочные модули и т.п.) | https://github.com/nasa/NASA-3D-Resources |
| **Cesium Moon Terrain** | Готовые 3D Tiles всей Луны (LOLA + LROC WAC) для CesiumJS. Нужен аккаунт Cesium ion. ⚠️ На форуме сообщают о смещении высот ~2,5 км относительно LOLA — не использовать для абсолютных высот | https://cesium.com/platform/cesium-ion/content/cesium-moon-terrain |

## 2. Рельеф южного полюса (радиогоризонт, тени)

| Источник | Что даёт | Ссылка |
|---|---|---|
| **PGDA — South Pole LOLA DEM Mosaic** | DEM 5 м/пиксель для 87–90° ю.ш. (GeoTIFF, полярная стереографическая проекция) | https://pgda.gsfc.nasa.gov/products/81 |
| **PGDA — A New View of the Lunar South Pole** | DEM 20 м/пиксель для 80–90° ю.ш. (Cloud-Optimized GeoTIFF, кадр MOON_ME) | https://pgda.gsfc.nasa.gov/products/90 |
| **PGDA — High-Resolution LOLA Topography for South Pole Sites** | DEM мест посадки с анализом неопределённости освещённости | https://pgda.gsfc.nasa.gov/products/78 |
| **PGDA — Shape-from-Shading DEMs** | Уточнённые DEM отдельных районов полюса (LOLA + снимки LROC NAC) | https://pgda.gsfc.nasa.gov/products/104 |
| **PDS Geosciences — LOLA** | Глобальные данные LOLA (для поиска по всей Луне) | https://pds-geosciences.wustl.edu/missions/lro/lola.htm |

## 3. Освещённость и температура

| Источник | Что даёт | Ссылка |
|---|---|---|
| **PGDA — Lunar Polar Illumination** (Mazarico et al., 2011) | Готовые карты средней освещённости полюсов за 18,6-летний цикл (240 и 60 м/пиксель). Подходит для валидации расчётов и быстрого фильтра «часы Солнца» | https://pgda.gsfc.nasa.gov/products/69 |
| **LRO Diviner (UCLA)** | Карты температуры поверхности, в том числе сезонные полярные продукты. Нужно для оценки температурного режима | https://www.diviner.ucla.edu/data |
| **LPI — Near-Surface Temperatures, South Pole 85°S–90°S** | Модельная карта температур у южного полюса | https://hdl.handle.net/20.500.11753/1336 |

## 4. Эфемериды: положение Солнца, Земли и Луны

| Источник | Что даёт | Ссылка |
|---|---|---|
| **Astronomy Engine** (JS/TS, npm `astronomy-engine`) | Положения Солнца и Луны, либрация, работает прямо в браузере. Точность ±1′. Подходит для живой анимации и календаря на десятки лет вперёд | https://github.com/cosinekitty/astronomy |
| **NAIF SPICE — generic kernels** | Эталонные эфемериды: `de440.bsp` (планеты), `moon_pa_de440_200625.bpc` + `moon_de440_220930.tf` (ориентация Луны), `earthstns_*.bsp` (станции DSN). Покрытие 1550–2650 | https://naif.jpl.nasa.gov/naif/data_generic.html |
| **SpiceyPy** (Python) | Обёртка SPICE для предрасчётов на бэкенде или в скриптах | https://github.com/AndrewAnnex/SpiceyPy |
| **TimeCraftJS** (NASA AMMOS) | SPICE в браузере через Emscripten (~20 МБ в lite-версии) | https://github.com/NASA-AMMOS/timecraftjs |
| **JPL Horizons API** | Эталон для проверки расчётов; поддерживает пользовательские топоцентрические точки на Луне | https://ssd-api.jpl.nasa.gov/doc/horizons.html |
| **astroquery.jplhorizons** | Python-клиент для Horizons | https://astroquery.readthedocs.io/en/stable/jplhorizons/jplhorizons.html |

## 5. Связь: Deep Space Network

| Источник | Что даёт | Ссылка |
|---|---|---|
| **DSN 810-005, модуль 301 (Coverage and Geometry)** | Точные координаты антенн DSN и маски горизонта станций | https://deepspace.jpl.nasa.gov/dsndocs/810-005/ |
| **NAIF earthstns kernel** | Координаты станций DSN в формате SPICE | https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/stations/ |
| **DSN Now** | Живая картина: какие антенны с какими аппаратами работают (для вдохновения UI) | https://eyes.nasa.gov/apps/dsn-now/ |

## 6. Места посадки и миссии

| Источник | Что даёт | Ссылка |
|---|---|---|
| **NASA — Artemis III candidate regions** | Сначала 13 районов (2022), затем 9 районов у южного полюса | https://www.nasa.gov/news-release/nasa-provides-update-on-artemis-iii-moon-landing-regions/ ⚠️ |
| **NASA — Artemis overview для Space Apps 2025** | Ограничения южного полюса: Солнце и Земля на высоте ~2–7°, двухнедельный цикл видимости Земли, уклоны < 10° | https://ntrs.nasa.gov/citations/20250009323 |
| **NASA CLPS** | Список миссий и мест посадки CLPS | https://www.nasa.gov/commercial-lunar-payload-services/ |

## 7. Запуски: стоимость, надёжность, космодромы

| Источник | Что даёт | Ссылка |
|---|---|---|
| **CSIS — Space Launch to LEO: How Much Does It Cost?** | Стоимость вывода 1 кг на НОО по ракетам (данные до 2019) | https://aerospace.csis.org/data/space-launch-to-low-earth-orbit-how-much-does-it-cost/ |
| **Our World in Data** | Тот же датасет в долларах 2021 года | https://ourworldindata.org/grapher/cost-space-launches-low-earth-orbit |
| **Jonathan McDowell — GCAT / Launch Log** | Полный журнал запусков: успешные и аварийные запуски по ракетам и космодромам (для расчёта вероятности аварии) | https://planet4589.org/space/gcat/ |

## 8. Готовые инструменты (для сравнения и вдохновения UI)

- **LROC QuickMap** — https://quickmap.lroc.asu.edu/
- **NASA Moon Trek** — https://trek.nasa.gov/moon/
- **NASA Eyes on the Solar System** — https://eyes.nasa.gov/apps/solar-system/
- **JPL Horizons (веб)** — https://ssd.jpl.nasa.gov/horizons/

---

## Рекомендуемый стек визуализации (предложение, не решение)

| Задача | Предложение | Почему |
|---|---|---|
| 3D-вид системы Земля–Луна / Солнце–Луна–Земля | **Three.js** (или react-three-fiber) | Полный контроль над сценой, масштабами и анимацией; текстуры из CGI Moon Kit и Blue Marble |
| Глобус Луны с выбором точки | **Three.js**, позже — **CesiumJS** с Cesium Moon Terrain | Three.js проще начать; Cesium даёт реальный рельеф «из коробки» |
| Эфемериды в браузере | **Astronomy Engine** | Лёгкий, быстрый, работает на десятки лет вперёд |
| Точные предрасчёты | **Python + SpiceyPy + DE440** | Эталонная точность; результат — JSON или бинарные тайлы для фронтенда |
| Маски горизонта для точек | **Python + rasterio/numpy** по DEM LOLA | Для каждой точки — профиль высоты горизонта по 360° азимута; при видимости Солнца/Земли сравниваем с ним |
| Графики (таймлайны, радар) | **D3.js** / **Recharts** / **ECharts** | Таймлайн окон, радар-диаграмма 4 факторов, тепловая карта окна запуска |

### Ключевая идея расчёта радиогоризонта
1. По DEM строим для точки **маску горизонта**: максимальный угол возвышения рельефа по каждому азимуту (0–360°).
2. По эфемеридам получаем азимут и высоту Солнца/Земли в топоцентрической системе точки на Луне.
3. Объект виден, если его высота выше маски на данном азимуте. Атмосферы нет, рефракцию не учитываем.
4. Для Солнца учитываем угловой диаметр (~0,53°): частичная видимость диска важна для батарей.
