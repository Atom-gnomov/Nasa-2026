# tools/ — скрипти передрозрахунків

Тут будуть Python-скрипти, які запускаються окремо від вебзастосунку:

- `build_globe_textures.py` — дані 3D-глобуса з офіційних джерел NASA → `data_cache/globe/`: колір CGI Moon Kit (SVS 4720), рельєф LOLA LDEM_16 і полярні LDEM_80S_80M / LDEM_875S_20M (PDS), маски горизонту для тіней. `--with-ldem64` — ще LDEM_64 (530 МБ) для `/api/elevation`. Залежності: `pip install tifffile imagecodecs Pillow numpy`. Повна збірка ~25 хв (маски горизонту). ✅
- `build_system_assets.py` — моделі 3D-виду системи з NASA 3D Resources → `data_cache/system/`: Сонце (glTF, NASA HEAT), Земля «Earth (A)» (USGS & NASA/JPL); Місяць бере текстуру з `build_globe_textures.py`. Без сторонніх залежностей, ~6 МБ. ✅
- `download_kernels.py` — завантаження ефемерид SPICE (DE440, PCK Місяця) у `data_cache/`.
- `build_horizon_masks.py` — маски горизонту для точок з DEM LOLA (див. `docs/RESOURCES.md`, розділ 2).
- `build_illumination_grid.py` — сітка «години Сонця / години зв'язку» для підбору локацій (друга черга).

Великі файли (`*.bsp`, `*.tif`) не комітимо — лише скрипти.
