# Джерела для візуалізації та розрахунків

Стартова точка для людей і агентів, які починають роботу над проєктом.
Вимоги до продукту — у [VISION.md](VISION.md), оригінальне завдання — у [CHALLENGE.md](CHALLENGE.md).

> Посилання зібрано 2026-11-09. Перед використанням перевіряйте актуальні версії файлів і ліцензії.
> Позначка ⚠️ означає, що джерело не перевірене повторно або має відомі застереження.

---

## 1. Текстури та 3D-моделі (вкладка «Місяць» і 3D-вид системи)

| Джерело | Що дає | Посилання |
|---|---|---|
| **NASA SVS — CGI Moon Kit** | Кольорова карта Місяця (LROC, до 16K) і карта висот LOLA (displacement) для 3D-глобуса. Основне джерело текстур для Three.js | https://svs.gsfc.nasa.gov/4720 |
| **NASA Visible Earth — Blue Marble** | Текстури Землі (день, ніч, хмари) для 3D-виду системи | https://visibleearth.nasa.gov/collection/1484/blue-marble |
| **NASA 3D Resources** | Готові 3D-моделі (LRO, посадкові модулі тощо) | https://github.com/nasa/NASA-3D-Resources |
| **Cesium Moon Terrain** | Готові 3D Tiles усього Місяця (LOLA + LROC WAC) для CesiumJS. Потрібен акаунт Cesium ion. ⚠️ На форумі повідомляють про зсув висот ~2,5 км відносно LOLA — не використовувати для абсолютних висот | https://cesium.com/platform/cesium-ion/content/cesium-moon-terrain |

## 2. Рельєф південного полюса (радіогоризонт, тіні)

| Джерело | Що дає | Посилання |
|---|---|---|
| **PGDA — South Pole LOLA DEM Mosaic** | DEM 5 м/піксель для 87–90° пд. ш. (GeoTIFF, полярна стереографічна проєкція) | https://pgda.gsfc.nasa.gov/products/81 |
| **PGDA — A New View of the Lunar South Pole** | DEM 20 м/піксель для 80–90° пд. ш. (Cloud-Optimized GeoTIFF, система MOON_ME) | https://pgda.gsfc.nasa.gov/products/90 |
| **PGDA — High-Resolution LOLA Topography for South Pole Sites** | DEM місць посадки з аналізом невизначеності освітленості | https://pgda.gsfc.nasa.gov/products/78 |
| **PGDA — Shape-from-Shading DEMs** | Уточнені DEM окремих районів полюса (LOLA + знімки LROC NAC) | https://pgda.gsfc.nasa.gov/products/104 |
| **PDS Geosciences — LOLA** | Глобальні дані LOLA (для пошуку по всьому Місяцю) | https://pds-geosciences.wustl.edu/missions/lro/lola.htm |

## 3. Освітленість і температура

| Джерело | Що дає | Посилання |
|---|---|---|
| **PGDA — Lunar Polar Illumination** (Mazarico et al., 2011) | Готові карти середньої освітленості полюсів за 18,6-річний цикл (240 і 60 м/піксель). Підходить для валідації розрахунків і швидкого фільтра «години Сонця» | https://pgda.gsfc.nasa.gov/products/69 |
| **LRO Diviner (UCLA)** | Карти температури поверхні, зокрема сезонні полярні продукти. Потрібно для оцінки температурного режиму | https://www.diviner.ucla.edu/data |
| **LPI — Near-Surface Temperatures, South Pole 85°S–90°S** | Модельна карта температур біля південного полюса | https://hdl.handle.net/20.500.11753/1336 |

## 4. Ефемериди: положення Сонця, Землі та Місяця

| Джерело | Що дає | Посилання |
|---|---|---|
| **Astronomy Engine** (JS/TS, npm `astronomy-engine`) | Положення Сонця й Місяця, лібрація, працює просто в браузері. Точність ±1′. Підходить для живої анімації та календаря на десятки років уперед | https://github.com/cosinekitty/astronomy |
| **NAIF SPICE — generic kernels** | Еталонні ефемериди: `de440.bsp` (планети), `moon_pa_de440_200625.bpc` + `moon_de440_220930.tf` (орієнтація Місяця), `earthstns_*.bsp` (станції DSN). Покриття 1550–2650 | https://naif.jpl.nasa.gov/naif/data_generic.html |
| **SpiceyPy** (Python) | Обгортка SPICE для передрозрахунків на бекенді або в скриптах | https://github.com/AndrewAnnex/SpiceyPy |
| **TimeCraftJS** (NASA AMMOS) | SPICE у браузері через Emscripten (~20 МБ у lite-версії) | https://github.com/NASA-AMMOS/timecraftjs |
| **JPL Horizons API** | Еталон для перевірки розрахунків; підтримує користувацькі топоцентричні точки на Місяці | https://ssd-api.jpl.nasa.gov/doc/horizons.html |
| **astroquery.jplhorizons** | Python-клієнт для Horizons | https://astroquery.readthedocs.io/en/stable/jplhorizons/jplhorizons.html |

## 5. Зв'язок: Deep Space Network

| Джерело | Що дає | Посилання |
|---|---|---|
| **DSN 810-005, модуль 301 (Coverage and Geometry)** | Точні координати антен DSN і маски горизонту станцій | https://deepspace.jpl.nasa.gov/dsndocs/810-005/ |
| **NAIF earthstns kernel** | Координати станцій DSN у форматі SPICE | https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/stations/ |
| **DSN Now** | Жива картина: які антени з якими апаратами працюють (для натхнення UI) | https://eyes.nasa.gov/apps/dsn-now/ |

## 6. Місця посадки та місії

| Джерело | Що дає | Посилання |
|---|---|---|
| **NASA — Artemis III candidate regions** | Спочатку 13 районів (2022), потім 9 районів біля південного полюса | https://www.nasa.gov/news-release/nasa-provides-update-on-artemis-iii-moon-landing-regions/ ⚠️ |
| **NASA — Artemis overview для Space Apps 2025** | Обмеження південного полюса: Сонце й Земля на висоті ~2–7°, двотижневий цикл видимості Землі, нахили < 10° | https://ntrs.nasa.gov/citations/20250009323 |
| **NASA CLPS** | Список місій і місць посадки CLPS | https://www.nasa.gov/commercial-lunar-payload-services/ |

## 7. Запуски: вартість, надійність, космодроми

| Джерело | Що дає | Посилання |
|---|---|---|
| **CSIS — Space Launch to LEO: How Much Does It Cost?** | Вартість виведення 1 кг на НОО за ракетами (дані до 2019) | https://aerospace.csis.org/data/space-launch-to-low-earth-orbit-how-much-does-it-cost/ |
| **Our World in Data** | Той самий датасет у доларах 2021 року | https://ourworldindata.org/grapher/cost-space-launches-low-earth-orbit |
| **Jonathan McDowell — GCAT / Launch Log** | Повний журнал запусків: успішні й аварійні запуски за ракетами та космодромами (для розрахунку ймовірності аварії) | https://planet4589.org/space/gcat/ |

## 8. Готові інструменти (для порівняння та натхнення UI)

- **LROC QuickMap** — https://quickmap.lroc.asu.edu/
- **NASA Moon Trek** — https://trek.nasa.gov/moon/
- **NASA Eyes on the Solar System** — https://eyes.nasa.gov/apps/solar-system/
- **JPL Horizons (веб)** — https://ssd.jpl.nasa.gov/horizons/

---

## Рекомендований стек візуалізації (пропозиція, не рішення)

| Задача | Пропозиція | Чому |
|---|---|---|
| 3D-вид системи Земля–Місяць / Сонце–Місяць–Земля | **Three.js** (або react-three-fiber) | Повний контроль над сценою, масштабами й анімацією; текстури з CGI Moon Kit і Blue Marble |
| Глобус Місяця з вибором точки | **Three.js**, пізніше — **CesiumJS** з Cesium Moon Terrain | З Three.js простіше почати; Cesium дає реальний рельєф «з коробки» |
| Ефемериди в браузері | **Astronomy Engine** | Легкий, швидкий, працює на десятки років уперед |
| Точні передрозрахунки | **Python + SpiceyPy + DE440** | Еталонна точність; результат — JSON або бінарні тайли для фронтенду |
| Маски горизонту для точок | **Python + rasterio/numpy** за DEM LOLA | Для кожної точки — профіль висоти горизонту по 360° азимута; під час перевірки видимості Сонця/Землі порівнюємо з ним |
| Графіки (таймлайни, радар) | **D3.js** / **Recharts** / **ECharts** | Таймлайн вікон, радар-діаграма факторів, теплова карта вікна запуску |

### Ключова ідея розрахунку радіогоризонту
1. За DEM будуємо для точки **маску горизонту**: максимальний кут піднесення рельєфу за кожним азимутом (0–360°).
2. За ефемеридами отримуємо азимут і висоту Сонця/Землі в топоцентричній системі точки на Місяці.
3. Об'єкт видно, якщо його висота вища за маску на цьому азимуті. Атмосфери немає, рефракцію не враховуємо.
4. Для Сонця враховуємо кутовий діаметр (~0,53°): часткова видимість диска важлива для батарей.
