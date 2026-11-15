# tools/ — скрипти передрозрахунків

Тут будуть Python-скрипти, які запускаються окремо від вебзастосунку:

- `build_globe_textures.py` — дані 3D-глобуса з офіційних джерел NASA → `data_cache/globe/`: колір CGI Moon Kit (SVS 4720), рельєф LOLA LDEM_16 і полярні LDEM_80S_80M / LDEM_875S_20M (PDS), маски горизонту для тіней. `--with-ldem64` — ще LDEM_64 (530 МБ) для `/api/elevation`. Залежності: `pip install tifffile imagecodecs Pillow numpy`. Повна збірка ~25 хв (маски горизонту). ✅
- `build_system_assets.py` — моделі 3D-виду системи з NASA 3D Resources → `data_cache/system/`: Сонце (glTF, NASA HEAT), Земля «Earth (A)» (USGS & NASA/JPL); Місяць бере текстуру з `build_globe_textures.py`. Без сторонніх залежностей, ~6 МБ. ✅
- `build_temperature_data.py` — температура LRO Diviner → `data_cache/temperature/`: GCP (0,5°, місцевий час кроком 15 хв, 2009–2015) і полярний PRP (річні T, глибина стабільного льоду, ~0,5 км). Лише numpy; ~3,4 ГБ завантаження, кілька хвилин обробки. ✅
- `download_kernels.py` — завантаження ефемерид SPICE (DE440, PCK Місяця) у `data_cache/`.
- `build_horizon_masks.py` — маски горизонту для точок з DEM LOLA (див. `docs/RESOURCES.md`, розділ 2).
- `build_illumination_grid.py` — сітка «години Сонця / години зв'язку» для підбору локацій (друга черга).
- `i18n_missing.py` — які українські тексти інтерфейсу ще не мають англійського перекладу (`app/static/js/i18n/en.json`); `--js` додає літерали JS.
- `build_starmap.py` — справжнє зоряне небо для фону: NASA SVS «Deep Star Maps 2020» (`starmap_2020_4k.exr`, ≈ 34 МБ; Hipparcos-2, Tycho-2, Gaia DR2) → `data_cache/starmap/starmap.jpg` (≈ 2,8 МБ). Потрібні лише для скрипта `OpenEXR`, `numpy`, `Pillow`; без карти лишається CSS-тло.
- `import_sky_pano.py` — панорама Чумацького Шляху з вашого GLB (Sketchfab «Sky Pano – Milkyway», CC BY-NC-SA 4.0, MozillaHubs) → `data_cache/starmap/pano.jpg` + `pano.json` з калібруванням орієнтації й подякою; основний фон, поки є, інакше карта NASA. Запуск: `python tools/import_sky_pano.py <файл.glb>`; потрібні `numpy`, `Pillow`.

Великі файли (`*.bsp`, `*.tif`) не комітимо — лише скрипти.
