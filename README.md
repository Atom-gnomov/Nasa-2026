# Lunar Mission Builder

A web application for planning a lunar mission on real NASA data, from choosing a landing point to a final report.
Backend: Flask (Python 3.13). Frontend: JavaScript with Three.js.

## Features

- **Moon**: interactive 3D globe, map and south-pole views; a surface view; a date and time calendar (UTC).
  Metrics at the selected point: surface height, slope, local solar time, horizon and open sky, Sun elevation and azimuth,
  time to sunset and sunrise, solar flux, panel output, Earth elevation, azimuth and visibility, surface temperature
  (LRO Diviner).
- **System**: a 3D view of the Sun–Earth–Moon system at real positions (NASA/JPL DE440 ephemerides).
- **Mission wizard** (the "Missions" button): planning steps saved as "My plan" and "My plans":
  1. name and goal (the goal pre-fills defaults for the later steps);
  2. mission type: uncrewed or crewed;
  3. landing region, date and point, chosen manually or by automatic selection;
  4. stay duration (crewed missions);
  5. crew or equipment;
  6. payload and supplies: category sizes, mass, cost, risk and flight time;
  7. launch vehicle and flight: rocket and launch-site compatibility, automatic selection, flight and trajectory simulation;
  8. consistency check: supplies against duration, mass against the rocket, lighting and Earth visibility over the stay
     (the longest night is taken from the calculation automatically);
  9. final report.
- **Selection**: finds the best landing point and window by priorities (energy, communications, radiation, temperature),
  compares candidates, and shows time series and charts.
- **Plan**: launch options by rocket, launch site, date and time, and trajectory.
- Interface languages: Ukrainian and English. Responsive layout for mobile screens.
- A loading screen with a spinning logo, a NASA star-map sky and a Milky Way panorama in the background.

## Running with Docker

A ready image is built by GitHub Actions and published to the registry:

```bash
docker run -p 8000:8000 -v lse-data:/data ghcr.io/atom-gnomov/nasa-2026:latest
```

Open http://localhost:8000. The `lse-data` volume keeps the NASA data between runs.

Build from source or run with Compose:

```bash
docker build -t lunar-mission-builder .
docker compose up -d --build
```

On first start the app downloads prepared data packs from the GitHub Release `data-v1` (about 285 MB: temperature,
3D resources, and the globe with terrain) and verifies their `sha256`. While the data is being prepared, the site shows
a loading screen.

### Cloudflare Containers

The `cloudflare/` directory contains a Worker that proxies requests to a container built from the `Dockerfile`.
Project settings in Cloudflare: Root directory `cloudflare`, Build command `npm install`, Deploy command
`npx wrangler deploy`. The Workers Paid plan is required. The container disk is ephemeral, so the data packs are
downloaded again after the container sleeps. Set the `SECRET_KEY` secret with `npx wrangler secret put SECRET_KEY`.

Configs for Fly.io (`fly.toml`) and Render (`render.yaml`) are included, and `compose.yaml` has an optional
Cloudflare Tunnel (`docker compose --profile tunnel up -d`).

## Running locally without Docker

```bash
python -m venv .venv
.venv\Scripts\activate        # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
flask --app app run
```

For development: `pip install -r requirements-dev.txt`, then run `pytest` (the JS tests in `tests/js` run with it when
Node is installed).

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORT` | `8000` | port inside the container |
| `WEB_CONCURRENCY` | `2` | number of gunicorn workers |
| `SECRET_KEY` | `dev-only-change-me` | Flask secret; set your own when hosting |
| `LSE_CACHE_DIR` | `data_cache` (`/data` in Docker) | directory for NASA data |
| `LSE_TEMP_DIR` | `<cache>/temperature` | directory for temperature data |
| `LSE_DEM_DIR` | `<cache>/globe/src` | LOLA terrain files |
| `LSE_AUTO_PREPARE` | `1` | whether to prepare data in the background |
| `LSE_AUTO_PREPARE_MODE` | `pack` | `pack` uses ready packs; `light`/`full` build from the `tools/` scripts |
| `LSE_AUTO_PREPARE_DATASETS` | `temperature,system` | datasets to prepare: `temperature`, `system`, `globe` |
| `LSE_EPHEMERIS_PATH` | the `naif-de440` package | path to the DE440 ephemerides |

## Layout

- `app/`: the application. `core/` holds astronomy and calculations, plus `services/`, `routes/` (pages and API),
  `static/` and `templates/`.
- `contracts/`: API schemas and examples.
- `tools/`: data preparation scripts and pack publishing (`build_data_pack.py`).
- `cloudflare/`: the Worker for Cloudflare Containers.
- `tests/`: Python and JS tests.

## Data sources and credits

NASA/JPL (DE440 ephemerides), LRO LOLA and LROC (lunar terrain and color), LRO Diviner (temperature), NASA SVS
"CGI Moon Kit" and "Deep Star Maps 2020" (Gaia DR2: ESA/Gaia/DPAC). The sky panorama is the Sketchfab model
"Sky Pano – Milkyway" (MozillaHubs), licensed CC BY-NC-SA 4.0: non-commercial use only.
