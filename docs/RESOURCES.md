# Джерела для візуалізації та розрахунків

Стартова точка для людей і агентів, які починають роботу над проєктом.
Вимоги до продукту — у [VISION.md](VISION.md), оригінальне завдання — у [CHALLENGE.md](CHALLENGE.md).

> Посилання зібрано 2026-11-09. Перед використанням перевіряйте актуальні версії файлів і ліцензії.
> Позначка ⚠️ означає, що джерело не перевірене повторно або має відомі застереження.

---

## 0. Офіційні ресурси завдання (вкладка Resources)

Ці джерела організатори дали як основні. Оригінальний текст — у [CHALLENGE.md](CHALLENGE.md). Нижче — **де саме брати дані** і для чого це в нашому проєкті.

| Ресурс | Що це | Звідки брати дані | Для чого нам |
|---|---|---|---|
| **LROC QuickMap** (ASU) — https://quickmap.lroc.asu.edu/ | інтерактивна карта: знімки високої роздільності, рельєф та інші набори даних LRO | зверніть увагу на шари рельєфу й освітленості та вигрузку фрагментів карти; ⚠️ який саме експорт доступний — перевірити в інтерфейсі | вибір і перевірка місць посадки (каталог `sites.json`), візуальна звірка нашого горизонту й рельєфу, складна топографія біля південного полюса |
| **NASA Moon Trek** — https://trek.nasa.gov/moon/ | 3D-візуалізація Місяця: поверхня, топографія, ділянки посадки | шари рельєфу й інструменти для вимірювань; ⚠️ чи є прямий доступ до даних (тайлів) — перевірити на сайті | звірка того, як рельєф впливає на горизонт; приклад інтерфейсу для 3D-виду |
| **JPL Horizons** — https://ssd.jpl.nasa.gov/horizons/ | розрахунок положень небесних тіл, зокрема Сонця й Землі **з будь-якої точки на Місяці** | веб-інтерфейс і API ([документація](https://ssd-api.jpl.nasa.gov/doc/horizons.html)): топоцентричний спостерігач на Місяці, кути місця й азимути в заданий час | **еталон для перевірки наших розрахунків** (кути Сонця й Землі в `app/core/ephemeris.py`); основа візуалізацій та оцінки енергії й зв'язку |
| **CSA — Moon Exploration** — https://www.asc-csa.gc.ca/eng/astronomy/moon-exploration/ | портал Канадського космічного агентства: минулі, поточні й майбутні місії, технології, участь в Artemis | контекстна інформація про місії й технології, не набір даних | довідка для освітньої частини й опису місій; ⚠️ набори даних тут не очікуємо |

**Як користуватися:**
- Для **перевірки математики** беріть Horizons: кілька точок і дат → порівняти з `/api/metrics` (див. тест із еталонними числами Horizons у контрактних тестах).
- Для **рельєфу й місць** — QuickMap і Moon Trek як візуальна звірка, а самі дані — з PDS (розділи 2–3 нижче).
- Організатори можуть додати ресурси до початку хакатону: перевіряти вкладку Resources на сторінці завдання й оновлювати цей розділ.

---

## 1. Текстури та 3D-моделі (вкладка «Місяць» і 3D-вид системи)

| Джерело | Що дає | Посилання |
|---|---|---|
| **NASA SVS — CGI Moon Kit** | Кольорова карта Місяця (LROC, до 16K) і карта висот LOLA (displacement) для 3D-глобуса. Основне джерело текстур для Three.js | https://svs.gsfc.nasa.gov/4720 |
| **NASA Visible Earth — Blue Marble** | Текстури Землі (день, ніч, хмари) для 3D-виду системи | https://visibleearth.nasa.gov/collection/1484/blue-marble |
| **NASA 3D Resources** | Готові 3D-моделі (LRO, посадкові модулі тощо) | https://github.com/nasa/NASA-3D-Resources |
| **NASA — Sun 3D Model (HEAT)** | ✅ (PR #12) Модель Сонця glTF (4 МБ) для 3D-виду системи; текстура світіння схематична | https://science.nasa.gov/learn/heat/resource/sun-3d-model/ |
| **NASA 3D Resources — Earth (A)** | ✅ (PR #12) Карта Землі 1440×720 (USGS & NASA/JPL): рельєф, розфарбований як суходіл/океан, не фото. «Earth» (STL для друку) і «Earth (B)» (фото диска Apollo 10) для кулі не підходять | https://science.nasa.gov/3d-resources/earth-a/ |
| **NASA SVS — Moon 3D Models (14959)** | GLB-моделі Місяця (колір, сітка, рельєф 8K). ⚠️ У варіантах із сіткою й рельєфом «стягнуті» полюси — для південного полюса не підходять; беремо вихідні карти CGI Moon Kit | https://svs.gsfc.nasa.gov/14959 |
| **Cesium Moon Terrain** | Готові 3D Tiles усього Місяця (LOLA + LROC WAC) для CesiumJS. Потрібен акаунт Cesium ion. ⚠️ На форумі повідомляють про зсув висот ~2,5 км відносно LOLA — не використовувати для абсолютних висот | https://cesium.com/platform/cesium-ion/content/cesium-moon-terrain |

## 2. Рельєф південного полюса (радіогоризонт, тіні)

| Джерело | Що дає | Посилання |
|---|---|---|
| **PGDA — South Pole LOLA DEM Mosaic** | DEM 5 м/піксель для 87–90° пд. ш. (GeoTIFF, полярна стереографічна проєкція) | https://pgda.gsfc.nasa.gov/products/81 |
| **PGDA — A New View of the Lunar South Pole** | DEM 20 м/піксель для 80–90° пд. ш. (Cloud-Optimized GeoTIFF, система MOON_ME) | https://pgda.gsfc.nasa.gov/products/90 |
| **PGDA — High-Resolution LOLA Topography for South Pole Sites** | DEM місць посадки з аналізом невизначеності освітленості | https://pgda.gsfc.nasa.gov/products/78 |
| **PGDA — Shape-from-Shading DEMs** | Уточнені DEM окремих районів полюса (LOLA + знімки LROC NAC) | https://pgda.gsfc.nasa.gov/products/104 |
| **PDS Geosciences — LOLA** | Глобальні дані LOLA (для пошуку по всьому Місяцю) | https://pds-geosciences.wustl.edu/missions/lro/lola.htm |
| **PDS — LOLA GDR (lrolol_1xxx)** | ✅ (PR #12) Використано: LDEM_16 і LDEM_64 (V3.1, циліндрична), LDEM_80S_80M і LDEM_875S_20M (V2.0, полярна стереографічна). Формати й проєкції — мітки .LBL і `catalog/dsmap*.cat` | https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/ |

## 3. Освітленість і температура

| Джерело | Що дає | Посилання |
|---|---|---|
| **PGDA — Lunar Polar Illumination** (Mazarico et al., 2011) | Готові карти середньої освітленості полюсів за 18,6-річний цикл (240 і 60 м/піксель). Підходить для валідації розрахунків і швидкого фільтра «години Сонця» | https://pgda.gsfc.nasa.gov/products/69 |
| **LRO Diviner (UCLA)** | Карти температури поверхні, зокрема сезонні полярні продукти. Потрібно для оцінки температурного режиму | https://www.diviner.ucla.edu/data |
| **PDS — Diviner GCP** (Williams et al., 2017) | ✅ (PR #12) Болометрична температура 0,5° × 0,5° за місцевим часом (бін 15 хв), 2009–2015; 18 смуг ASCII по ~156 МБ | https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_gcp/ |
| **PDS — Diviner PRP, південь** (Paige et al., 2010) | ✅ (PR #12) Трикутна сітка ~0,5 км (квадрат 600 × 600 км): річні середня й максимум T, глибина стабільного льоду. Код льоду −1 у мітці не описаний (див. MATH.md §11.1) | https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_prp/ |
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
| **DSN 810-005, модуль 301 (Coverage and Geometry), Rev. P** | Точні координати антен DSN (табл. 5, WGS 84, ±3 см), нижня межа передавання 10,1° (§2.2.4), механічна межа ≈ 6° (§2.2.2), маски горизонту за азимутом (рис. 10–25). Використано в `app/data/dsn_stations.json` (D2, PR #29) | https://deepspace.jpl.nasa.gov/dsndocs/810-005/301/301P.pdf |
| **NAIF earthstns kernel** | Координати станцій DSN у форматі SPICE | https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/stations/ |
| **DSN Now** | Жива картина: які антени з якими апаратами працюють (для натхнення UI) | https://eyes.nasa.gov/apps/dsn-now/ |

## 6. Місця посадки та місії

| Джерело | Що дає | Посилання |
|---|---|---|
| **NASA — Artemis III candidate regions** | Спочатку 13 районів (2022), потім 9 районів біля південного полюса | https://www.nasa.gov/news-release/nasa-provides-update-on-artemis-iii-moon-landing-regions/ ⚠️ |
| **NASA — Artemis overview для Space Apps 2025** | Обмеження південного полюса: Сонце й Земля на висоті ~2–7°, двотижневий цикл видимості Землі, нахили < 10° | https://ntrs.nasa.gov/citations/20250009323 |
| **NASA CLPS** | Список місій і місць посадки CLPS | https://www.nasa.gov/commercial-lunar-payload-services/ |
| **NASA-STD-3001, Vol. 1, Rev. C (2023)** | Радіаційні ліміти екіпажу: кар'єрна ефективна доза < 600 мЗв [V1 4030], сонячна протонна подія < 250 мЗв [V1 4031], ліміти органів за 30 діб / рік (табл. 4.8-1). Використано в `app/data/mission_thresholds.json` (D5, PR #30) | https://standards.nasa.gov/sites/default/files/standards/NASA/C/nasa-std-3001-vol-1-rev-c-signature.pdf |
| **Artemis Human Landing System Update (NASA, 2024)** | «Key Artemis III Landing Requirements» (с. 19): нахил посадки (100 м) < 10°, EVA (2 км) < 20°, зв'язок напряму із Землею; фільтри аналізу: видимість Землі ≥ 25 %, Сонця ≥ 5 % (с. 23–24). D5 | https://ntrs.nasa.gov/citations/20240009596 |
| **NASA OIG IG-26-004 (2026)** | Нахил посадкового модуля після посадки ≤ 8° для дій екіпажу (с. 30). D5 | https://oig.nasa.gov/wp-content/uploads/2026/03/final-report-ig-26-004-nasas-management-of-the-human-landing-system-contracts.pdf |

## 7. Запуски: вартість, надійність, космодроми

| Джерело | Що дає | Посилання |
|---|---|---|
| **CSIS — Space Launch to LEO: How Much Does It Cost?** | Вартість виведення 1 кг на НОО за ракетами (дані до 2019) | https://aerospace.csis.org/data/space-launch-to-low-earth-orbit-how-much-does-it-cost/ |
| **Our World in Data** | Той самий датасет у доларах 2021 року | https://ourworldindata.org/grapher/cost-space-launches-low-earth-orbit |
| **Ariane 6 User's Manual, Issue 2 Rev. 0 (2021)** | Координати стартового комплексу Ariane 6 у Куру, §6.2.3.2: записано як «5°26’46’’ N, 52°79’22’’ W (TBC)» — це десяткові градуси 5,2646° / −52,7922° (D2) | https://ariane.group/app/uploads/sites/4/2024/10/Mua-6_Issue-2_Revision-0_March-2021.pdf |
| **Jonathan McDowell — GCAT / Launch Log** | Повний журнал запусків: успішні й аварійні запуски за ракетами та космодромами (для розрахунку ймовірності аварії) | https://planet4589.org/space/gcat/ |

**Оптимальна траса, космодроми, нестандартні старти, нові ракети (знайдено 2026-11-14 для задач M10, M19, M20, D6, D7).**
Нижче — **вторинні джерела** (пошук); кожне число перед використанням у даних звіряти з першоджерелом (D6, D7). Розбіжності між джерелами позначені прямо.

| Джерело | Що дає | Посилання |
|---|---|---|
| **NASA NTRS 20080034478** — проєктування місії CEV/LSAM | TLI ≈ 3150 м/с для ступеня відльоту; для частини місць посадки нахил і вузол орбіти навколо Місяця змушують робити триімпульсне гальмування біля Місяця (LOI) | https://ntrs.nasa.gov/citations/20080034478 |
| **ISSFD 2024, робота 18-1** — низькоенергетичні переходи | Енергетично вигідні переходи можуть давати від'ємну вартість гальмування (балістичний захват); політ триває місяці й відходить на 1–1,5 млн км | https://issfd.org/ISSFD_2024/ISSFD2024_18-1.pdf |
| **Miller, Belbruno (1991)** — перехід до Місяця з балістичним захватом | Межа слабкої стійкості (WSB): економія ≈ 100–200 м/с (5–10 % палива); інше джерело — до 0,4 км/с. **Оцінки розходяться** — залежать від опорного випадку | https://ui.adsabs.harvard.edu/abs/1991sfm..proc...97M/abstract |
| **Wikipedia — Low-energy transfer** | Огляд місій з балістичним захватом: Hiten, GRAIL, CAPSTONE, Danuri, Hakuto-R M1; зіставлення «час ↔ Δv» | https://en.wikipedia.org/wiki/Low-energy_transfer |
| **MathWorks — Trans-Lunar Trajectory Optimization (OTB)** | Відкритий приклад: мінімальний Δv TLI з розв'язку задачі Ламберта (двотільна), далі уточнення методом стрільби в n-тільній моделі — зразок для звірки наших розрахунків | https://www.mathworks.com/matlabcentral/fileexchange/73600-trans-lunar-trajectory-optimization-otb |
| **ISSFD 2004, P1121** — вікна запуску до Місяця | Майданчик закріплений в Землі, тож змінна лише година виведення на НОО — вона задає напрям площини НОО в інерціальній системі | https://www.issfd.org/ISSFD_2004/papers/P1121.pdf |
| **Wikipedia — List of rocket launch sites** | Індекс космодромів світу з координатами (для D6; координати брати з першоджерел, не з вікі) | https://en.wikipedia.org/wiki/List_of_rocket_launch_sites |
| **Wikipedia — Sea Launch, Zenit-3SL** | Платформа «Одіссей» на екваторі ≈ 154° зх., ≈ 370 км на схід від Кірітімаці; 36 запусків, 32 успішні; Chapter 11 у 2009 р.; GTO ≈ 6 000–6 160 кг (джерела розходяться); статус — не діюча | https://en.wikipedia.org/wiki/Sea_Launch |
| **Wikipedia — Stratolaunch Roc** | Літак-носій: вантажопідйомність ≈ 250 т (це не маса виводимого на орбіту); розробку власних ракет зупинено 2019 р., далі — гіперзвуковий Talon-A | https://en.wikipedia.org/wiki/Stratolaunch_Roc |
| **SatNews, 2026-07 — «Air launch died the same week responsive space arrived»** | Останній політ Pegasus XL 3 липня 2026 р. (46-й, поблизу Кваджалейна) завершив єдину діючу орбітальну систему повітряного старту; Pegasus XL — ≈ 370 кг на НОО (джерела: 360–443 кг) | https://satnews.com/2026/07/13/air-launch-died-the-same-week-responsive-space-arrived/ |
| **NASA Science — «Mission To Boost NASA's Swift Launches From Marshall Islands» (2026-07-03)** | Pegasus XL з Кваджалейна 3 липня 2026: 8:36 вечора за маршалловим часом (4:36 EDT), скидання ≈ 40 000 фт (D6, PR #60) | https://science.nasa.gov/blogs/swift/2026/07/03/mission-to-boost-nasas-swift-launches-from-marshall-islands/ |
| **Via Satellite — «Mission to Rescue NASA Swift Observatory Launches» (2026-07-06)** | «46th Pegasus launch to date», «first time Pegasus has launched since 2021»; слів про «останній політ» немає; дата запуску в статті («July 2») розходиться з NASA (D6, PR #60) | https://www.satellitetoday.com/launch/2026/07/06/mission-to-rescue-nasa-swift-observatory-launches/ |
| **CNES CSG — «The first Ariane 64 successfully launches 32 Amazon LEO satellites» (2026-02-13)** | Перший Ariane 64, місія VA267, 12.02.2026, 32 супутники Amazon Leo (D6, PR #60) | https://centrespatialguyanais.cnes.fr/en/succes-va267 |
| **ArianeGroup — «VA267: Ariane 64 Ready for its First Mission for Amazon Leo» (2026-02-09)** | Оголошення першого польоту Ariane 64, 18 польотів Ariane 6 для Amazon Leo (D6, PR #60) | https://www.ariane.group/en/news/va267-ariane-64-ready-for-its-first-mission-for-amazon-leo/ |
| **NASA/TP-2015-218570/REV2 Life Support BVAD (2022)** | Їжа, кисень, вода на люд·добу; житловий об'єм; маса житла на м³; сонячні батареї й акумулятори на поверхні Місяця; терморегуляція (D4, PR #69) | https://ntrs.nasa.gov/api/citations/20210024855/downloads/BVAD_2.15.22-final.pdf |
| **NASA HRP — Minimum Acceptable Net Habitable Volume (2014)** | Мінімум 25 м³ житлового об'єму на людину для довгих місій (D4, PR #69) | https://ntrs.nasa.gov/api/citations/20140016951/downloads/20140016951.pdf |
| **NASA SST State of the Art — 3.0 Power (2024)** | Питома потужність сонячних батарей (~30 Вт/кг), Li-ion 100–265 Вт·год/кг (D4, PR #69) | https://www.nasa.gov/wp-content/uploads/2025/02/3-soa-power-2024.pdf |
| **NASA OIG IG-24-013 — CLPS (2024)** | Доставка на Місяць ≈ $1 млн/кг (2019) → ≈ $1,2 млн/кг (2023); маси перших вантажів (D4, PR #69) | https://oig.nasa.gov/wp-content/uploads/2024/06/final-report-ig-24-013-nasas-commercial-lunar-payload-services-initiative.pdf |
| **NASA OIG IG-22-010 — VIPER (2022)** | Маса VIPER 475 кг, вартість проєкту $433,5 млн без доставки (D4, PR #69) | https://oig.nasa.gov/wp-content/uploads/2024/02/IG-22-010.pdf |
| **NASA OIG IG-18-016 — Commercial Resupply Services (2018)** | Вантаж на МКС: $63 200/кг (CRS-1), $71 800/кг (CRS-2, прогноз) (D4, PR #69) | https://oig.nasa.gov/wp-content/uploads/2024/02/IG-18-016.pdf |
| **AIAA, 2026-06-10 — «Growing Launch Demand Revives Interest in Offshore Rocket Operations»** | Відновлення інтересу до морських стартів; Lockheed Martin, Firefly і Seagate — морська платформа для Alpha, цільова готовність кінець 2027 р. (≈ ABS Approval in Principle, грудень 2025) | https://aiaa.org/2026/06/10/growing-launch-demand-revives-interest-in-offshore-rocket-operations/ |
| **SatNews, 2026-05-14 — Starship V3** | Заявлено ≥ 100 т на НОО (у перспективі до 200 т); мета — повна багаторазовість | https://satnews.com/2026/05/14/spacex-debuts-starship-v3-redefining-heavy-lift-launch-capability/ |
| **Wikipedia — New Glenn** | 7×2 — 45 т на НОО; 9×4 (у розробці) — ≥ 70 т; у травні 2026 р. вибух на майданчику LC-36, відновлення польотів — з 22 травня | https://en.wikipedia.org/wiki/New_Glenn |
| **Wikipedia — Long March 10** | ≈ 27 т на траєкторію до Місяця (TLI), ≈ 70 т на НОО — **проєктні цілі**, не підтверджені польотом | https://en.wikipedia.org/wiki/Long_March_10 |
| **Wikipedia — Ariane 6; newspaceeconomy.ca 2026-02-16** | Ariane 64: ≈ 21 650 кг на НОО, ≈ 11 500 кг на GTO; з покращеними P160C — ≈ 22 т. **Розбіжності між джерелами** | https://newspaceeconomy.ca/2026/02/16/the-ariane-6-rocket-gets-more-oomph/ |
| **Aerospace Corp. (CSPS), Jones, 2026-06 — Super Heavy Lift** | Порівняння надважких: SLS Block 1 ≈ 70 т на НОО; Falcon Heavy ≈ 64 т (інші таблиці — 57 т) | https://csps.aerospace.org/sites/default/files/2026-06/Jones_SuperHeavyLift_FINAL20260614.pdf |
| **Wikipedia — Starship HLS** | Для посадки потрібне дозаправлення на орбіті: оцінки — від 4 до ≈ 19 танкерних запусків; графік Artemis III змінювався (2026–2028) | https://en.wikipedia.org/wiki/Starship_HLS |

**Каталог ракет D7 (`app/data/rockets.json`, PR #49, перевірено 2026-11-14) — першоджерела:** сторінки виробників SpaceX (Falcon 9, Falcon Heavy, Starship: https://www.spacex.com/vehicles/), Blue Origin (New Glenn і 9x4: https://www.blueorigin.com/new-glenn), ULA (таблиця Vulcan Centaur з TLI при C3 = −2 км²/с²: https://www.ulalaunch.com/rockets/vulcan-centaur), NASA (SLS Block 1 — понад 27 т до Місяця: https://www.nasa.gov/reference/space-launch-system/). Long March 10 — лише вторинне (Wikipedia). Сторінки SpaceX і Blue Origin рендеряться скриптом — звичайне завантаження HTML їх не бачить, читати в браузері. Після D7 лишаються прогалини: TLI для Falcon Heavy і Ariane 6; ціни запуску на НОО з першоджерел (D4); Ванденберг і Starbase відсутні в `launch_sites.json`.

**Прогалини, які ще треба закрити за першоджерелом (D7):** TLI-місткість Falcon Heavy, Ariane 6 і Vulcan; офіційні посібники користувача (Falcon, Ariane 6, Vulcan, New Glenn); маса, що сідає на поверхню, для Starship HLS і Blue Moon MK1; обмеження азимутів безпеки запуску (для Вандерберга джерела розходяться: 140–201° проти 170–240°).

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
