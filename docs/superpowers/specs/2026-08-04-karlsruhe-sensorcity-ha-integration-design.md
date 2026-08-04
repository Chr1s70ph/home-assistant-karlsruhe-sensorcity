# Karlsruhe SensorCity — Home Assistant Integration (Design Spec)

- **Date:** 2026-08-04
- **Status:** Approved (awaiting user spec review)
- **Owner:** user
- **Component domain:** `karlsruhe_sensorcity`
- **HACS category:** integration
- **HA IoT class:** `cloud_polling`

## 1. Background

The City of Karlsruhe publishes a public "SensorCity" sensor network behind an
Esri Experience Builder dashboard at
`https://geoportal.karlsruhe.de/sensorcity/Dashboard/`. The dashboard is backed
by a **public, read-only ArcGIS REST FeatureServer** — no API key, no
authentication, just HTTP GET. There is **no existing Home Assistant / HACS
integration** for it (confirmed via GitHub and DuckDuckGo searches; existing
Karlsruhe HA projects cover only KVV transit and canteen plans).

The user wants to bring these sensors into Home Assistant, selecting which
sensor stations to expose and getting all of that station's readings as proper
HA entities.

### Community references (not HA, but document the API)
- `maxliesegang/ka-sensorcity-explorer` — React app; best API reference at
  `karlsruhe_sensorcity_api.md`.
- `matze/sensorcity` — minimal vanilla-JS dashboard; `js/api.js` shows the query
  pattern.

## 2. Goals

1. A HACS-installable custom component that exposes Karlsruhe SensorCity data in
   Home Assistant.
2. **Auto-discover** all available stations from the live layer.
3. Let the user **select specific stations** from a single searchable list in the
   config flow; expose **all measurements** for each selected station.
4. **Live+ mode**: weather stations also receive PM10/PM2.5, UV-A/UV-B, wind
   speed, and precipitation from the newest archive row (near-real-time, not a
   history series).
5. An **options flow** to add/remove stations and adjust polling interval without
   re-adding the integration.
6. Proper HA semantics: device grouping, device classes, units, state classes
   (so long-term statistics work), and sensible unavailable handling.

## 3. Non-goals (v1)

- Historical time-series ingestion from archive layers 2–4 (rolling windows of
  weeks/months). The "live+" archive fetch reads only the single newest row per
  selected weather station, not a series.
- Writing data back; the service is treated as strictly read-only.
- Automatic area/radius-based station discovery (manual list selection only).
- Deriving rainfall in mm from rain-gauge `clicks` (expose raw counter only;
  mm derivation is a possible future enhancement).

## 4. Data source

**Base URL**
```
https://geoportal.karlsruhe.de/ags04/rest/services/Hosted/Sensordaten_NodeRED/FeatureServer
```
Append `?f=json` for service/layer metadata. Query endpoint:
`GET {BASE}/{layerId}/query`. `maxRecordCount` = **2000**; responses set
`exceededTransferLimit` when more remain. Output format `f=json` (or `geojson`).
`f=csv` is **not** supported on `/query`.

### Layers

| ID | Name | Use | Records |
|----|------|-----|--------|
| 1 | `Sensordaten_Update` | **Primary.** Latest row per sensor. | 196 (live) |
| 2 | `NodeRED_Temperatur_Archiv` | **Live+ enrichment** (newest row only). | ~498k rolling ~5 wk |
| 3 | `NodeRED_Regenschreiber_Archiv` | Not used in v1. | ~40k |
| 4 | `NodeRED_Bodensensoren_Archiv` | Not used in v1. | ~5k |

### Station inventory (layer 1, observed 2026-08-04, total 196)

| Count | `beschreibung` | Live-layer measurement fields |
|------:|----------------|-------------------------------|
| 92 | `Temperatur-Sensor` | `temp`, `luftfeuchte`, `press`, `sonnenstrahlung`, `batteriestatus` |
| 99 | `Boden-Sensor` | `soil_moisture_at_depth_0..5`, `soil_temperature_at_depth_0..5`, `battery_voltage` |
| 3 | `Wasserpegel-Sensor` | `pegel` |
| 2 | `Regenschreiber` | `clicks` |

### Live+ extra fields (layer 2, newest row per weather station)

`pm10`, `pm25`, `uv_a_strahlung`, `uv_b_strahlung`, `windgeschwindigkeit`,
`niederschlag` (plus the same core fields as layer 1). Layer 2's newest
`measured_at` observed at 2026-08-04T16:36 UTC — i.e. near-real-time.

### Key fields & conventions

- `measured_at`, `inserted_at` — epoch **milliseconds**, UTC. Divide by 1000 for
  seconds; render ISO 8601 in attributes.
- `device_id` — stable per-sensor key (UUID for temp/soil/rain; numeric string
  e.g. `9016` for water gauges). Used as the HA device identifier and unique-id
  stem.
- `name` — station label, e.g. `170 - Elsa-Brändström-Straße (Bergwald)`. Note:
  some rain-gauge names contain URL-encoded substrings (e.g. `%5B…%5D`) —
  decode before display.
- `beschreibung` — category; used for device model and to pick the measurement
  registry.
- `stadtteil` — district; used as HA device area suggestion.
- `standort`, `quelle`, `temperaturkategorien` (temp), `baumart` (soil) —
  exposed as entity/device attributes where relevant.
- Geometry: most rows carry `geometry.x` (lon) / `geometry.y` (lat); water
  gauges also expose `lat`/`lon` attributes. Used for device location.

### Unit & sentinel conventions (verified against samples)

- `press` is in **Pascals** (sample 98295 → 982.95 hPa). Convert to **hPa**
  (divide by 100) for HA.
- `sonnenstrahlung` in **W/m²** (irradiance).
- Soil `soil_temperature_at_depth_*` in **°C**; `soil_moisture_at_depth_*` in
  **%**. Field suffix is `0X1` where `X` is the band number 0–7. **Bands 0–5
  hold real readings; bands 6 and 7 are the device's not-connected sentinels**
  (`-327.68` °C and `-5` %). Bands 6–7 must be skipped entirely (never exposed).
- `pegel` in **cm** (water level).
- `clicks` is a **cumulative** tipping-bucket count → `state_class
  total_increasing`.
- `batteriestatus` / `battery_voltage` in **V** (LiPo, ~3.0–4.2 V).

### Live+ units (layer 2; to be confirmed against live value ranges at
implementation, adjusted only if the source clearly uses other units)

- `pm10`, `pm25` → **µg/m³**, state_class measurement, no device class.
- `uv_a_strahlung`, `uv_b_strahlung` → **W/m²**, device_class irradiance.
- `windgeschwindigkeit` → **m/s**, device_class wind_speed.
- `niederschlag` → **mm**, device_class precipitation, state_class measurement.

## 5. Approach (selected: A — single entry, dynamic entities)

| | A. Single entry, dynamic entities ✅ | B. One entry per station | C. Create all 196, disable in UI |
|---|---|---|---|
| Setup | One flow, pick stations | Repeat per station | Zero-config |
| API calls/cycle | 1 (all rows, filter) | 1 per station | 1 |
| Entity count | Only your picks | Only your picks | 2000+ upfront |
| Edit later | Options flow | Add/delete entries | Disable in UI |

**Chosen: A.** One config entry, one `DataUpdateCoordinator`, one request per
poll. The options flow edits the station set and scan interval. This matches the
user's "pick stations from a single searchable list" decision and bounds entity
count to the user's selection.

## 6. Architecture

```
custom_components/karlsruhe_sensorcity/
  manifest.json        # HA metadata, iot_class=cloud_polling, config_flow=true
  __init__.py          # async_setup_entry / async_unload_entry / update listeners
  const.py             # DOMAIN, endpoints, defaults, measurement registry seed
  arcgis.py            # Pure-Python ArcGIS REST client (query, paginate, decode)
  models.py            # Station dataclass; Measurement mapping type
  coordinator.py       # DataUpdateCoordinator: fetch+filter+live+ enrichment
  entity.py            # KarlsruheSensorCityEntity base (device info, attributes)
  sensor.py            # SensorEntity per measurement; async_setup_entry
  config_flow.py       # user step (station multi-select) + options flow
  strings.json         # config/options UI strings (en; de optional)
repo root:
  hacs.json  README.md  info.md  requirements_test.txt  tests/  .github/
```

### Module responsibilities

- **`arcgis.py`** — typed, HA-independent client. `query(layer, where,
  outFields, orderByFields, resultOffset, resultRecordCount, returnGeometry)`,
  auto-paginates when `exceededTransferLimit`, decodes epoch-ms, returns list of
  attribute dicts (+ geometry). Pure-Python so it is unit-testable without HA.
- **`models.py`** — `Station` dataclass (`device_id`, `name`, `beschreibung`,
  `lat`, `lon`, `stadtteil`, `standort`, `quelle`, attrs) and a `Measurement`
  descriptor (`field`, `label`, `device_class`, `unit`, `state_class`,
  `entity_category`). A registry maps `(category, field) → Measurement`.
- **`coordinator.py`** — `DataUpdateCoordinator` subclass. Each cycle:
  1. Query layer 1 `where=1=1` (196 rows < 2000, single page),
     `returnGeometry=true`, `outFields=*`.
  2. Filter to the entry's selected `device_id`s.
  3. For each selected weather (`Temperatur-Sensor`) station, fetch the newest
     layer-2 row: `where=device_id='…'&orderByFields=measured_at DESC
     &resultRecordCount=1&returnGeometry=false`, and merge its extra fields onto
     the station record. (One small request per selected weather station.)
  4. Return `{device_id: Station}`.
- **`entity.py`** — base entity building `DeviceInfo` from a `Station` and
  supplying shared attributes (`measured_at` ISO, `quelle`, `standort`,
  category-specific extras).
- **`sensor.py`** — `async_setup_entry` reads the selected stations and, for
  each, iterates the measurement registry for that station's category, creating
  one `SensorEntity` per applicable measurement. Soil bands 6–7 are not
  generated. Each entity pulls its value from `coordinator.data[device_id]`.
- **`config_flow.py`** — see §7.

### Data flow

```
HA startup → async_setup_entry → coordinator (first refresh) → sensor platform
                |                          |
                |                          └→ arcgis.query(layer 1) + live+ (layer 2)
                └→ create entities per selected station/measurement
Poll (scan_interval) → coordinator.async_refresh → entities.async_write_ha_state
Options flow (add/remove station / interval) → reload entry → entities rebuilt
```

## 7. Config & options flow

### User step (`config_flow.py`)
1. Fetch all stations from layer 1 (single query, paginated if ever > 2000).
2. Build `dict[str, str]` = `{device_id: "NNN – Name (Category)"}` for a
   `vol.Required("stations"): cv.multi_select(...)`. Category is appended so the
   one list stays disambiguable across types.
3. User selects any number of stations; validate `len >= 1` else show error.
4. Create config entry with `data = {"stations": [device_id, ...]}` and
   `options = {"scan_interval": 5}`; title `"Karlsruhe SensorCity"`.

### Options flow
- Re-render the same station multi-select, pre-filled with the current
  selection, so the user can add/remove stations.
- A numeric `scan_interval` field (minutes), default 5, range 1–60.
- On submit, update entry data/options and trigger entry reload so entities are
  rebuilt (added stations get entities; removed stations' entities are
  orphaned and cleaned by HA's entity registry).

### Strings
`strings.json` provides titles, descriptions, and field labels for both flows
(in English; German optional via `translations/de.json`).

## 8. Entity model

### Device (one per station)
- `identifiers = {(DOMAIN, device_id)}`
- `name = station.name` (URL-decoded for rain gauges)
- `model = station.beschreibung` (e.g. `Temperatur-Sensor`)
- `manufacturer = station.quelle` (`Stadt Karlsruhe`, `HVZ/RP Karlsruhe`, …)
- `sw_version = protocol_version` when present
- `suggested_area = stadtteil`
- lat/lon from geometry (or `lat`/`lon` attrs for water gauges)

### Entities (one per measurement; unique id `f"{device_id}_{field}"`)

| Category | Field(s) | device_class | unit | state_class | notes |
|----------|----------|--------------|------|-------------|-------|
| Temperatur | `temp` | temperature | °C | measurement | |
| Temperatur | `luftfeuchte` | humidity | % | measurement | |
| Temperatur | `press` | pressure | hPa | measurement | Pa/100 |
| Temperatur | `sonnenstrahlung` | irradiance | W/m² | measurement | |
| Temperatur (live+) | `pm10`, `pm25` | — | µg/m³ | measurement | |
| Temperatur (live+) | `uv_a_strahlung`, `uv_b_strahlung` | irradiance | W/m² | measurement | |
| Temperatur (live+) | `windgeschwindigkeit` | wind_speed | m/s | measurement | |
| Temperatur (live+) | `niederschlag` | precipitation | mm | measurement | |
| Boden | `soil_moisture_at_depth_0..5` | moisture | % | measurement | 6 entities, label "Soil moisture (depth N)" |
| Boden | `soil_temperature_at_depth_0..5` | temperature | °C | measurement | 6 entities, label "Soil temperature (depth N)" |
| Wasserpegel | `pegel` | distance | cm | measurement | "Water level" |
| Regenschreiber | `clicks` | — | tips | total_increasing | "Rain counter" |
| any (where present) | `batteriestatus` / `battery_voltage` | voltage | V | measurement | entity_category diagnostic |

### State & availability
- State = the field's numeric value (or counter for `clicks`).
- Unavailable when: station absent from the latest poll, field is `null`, or
  value is a known sentinel (soil bands 6–7 — but those entities are not
  created at all).
- Attributes: `measured_at` (ISO 8601), `quelle`, `standort`, `stadtteil`, and
  category extras (`temperaturkategorien` for temp, `baumart` for soil).
- `state_class=measurement` on measurement entities enables long-term
  statistics; `clicks` uses `total_increasing`.

## 9. Polling & performance

- Default scan interval **300 s** (5 min), configurable 60–3600 s.
- Per cycle: 1 layer-1 request (all rows) + 1 layer-2 request per selected
  weather station. For a typical selection of a few stations this is a handful
  of small JSON requests per 5 min — negligible load on a public service.
- 196 live rows is well under the 2000 page limit, so layer-1 fetch is a single
  request. The client still paginates defensively for future growth.
- Coordinator uses HA's standard update grouping; all entities share one
  coordinator so there is exactly one refresh per interval regardless of entity
  count.

## 10. Error handling & robustness

- Network/HTTP/JSON errors in the coordinator are wrapped as
  `UpdateFailed`; HA marks entities unavailable and retries next cycle.
- Config flow fetch failure shows an error with a retry (re-run the station
  fetch).
- Sentinels and `null` fields never produce a numeric state — the entity is
  unavailable instead.
- URL-encoding of query parameters (spaces, quotes, `%`, `[`, `{`) is handled by
  the client.
- The service is treated as read-only even though it advertises edit
  capabilities.

## 11. Testing

- `requirements_test.txt`: `pytest`, `pytest-homeassistant-custom-component`,
  `aiohttp`.
- Fixtures: captured real JSON from layers 1 and 2 (already sampled) committed
  under `tests/fixtures/`.
- `test_arcgis.py` — query construction, pagination over `exceededTransferLimit`,
  epoch-ms decode, sentinel detection, geometry parsing. Pure-Python, no HA.
- `test_coordinator.py` — filtering to selected stations, live+ enrichment
  merge, `UpdateFailed` on HTTP error (using `aiohttp`/`aresponses`).
- `test_sensor.py` — entity generation per category, correct device classes /
  units / state classes, soil bands 6–7 excluded, unavailable on null/sentinel,
  device info mapping.
- `test_config_flow.py` — station multi-select populates from a mocked client,
  validation of empty selection, options flow add/remove + scan interval, entry
  reload triggers entity rebuild.

## 12. Packaging

- `manifest.json`:
  ```json
  {
    "domain": "karlsruhe_sensorcity",
    "name": "Karlsruhe SensorCity",
    "documentation": "REPO_URL",
    "issue_github": "REPO_URL/issues",
    "codeowners": ["GITHUB_USERNAME"],
    "config_flow": true,
    "iot_class": "cloud_polling",
    "version": "0.1.0"
  }
  ```
  No `requirements` — uses HA's bundled `aiohttp`. `REPO_URL` and
  `GITHUB_USERNAME` are supplied from the user's own GitHub repository at
  packaging time (these are the only values that depend on the user and cannot
  be known from the API/design).
- `hacs.json`:
  ```json
  { "name": "Karlsruhe SensorCity", "render_readme": true, "content_in_root": false }
  ```
  (HACS discovers the integration via `custom_components/karlsruhe_sensorcity/`.)
- `README.md` — install (HACS custom repo + download), configuration walkthrough
  (add integration → pick stations → options), data source & limitations.
- `info.md` — one-paragraph HACS listing description.

## 13. Out of scope / future

- Archive history ingestion (layers 2–4 rolling windows) for long-term charts.
- Rainfall mm derivation from `clicks` (e.g. ×0.2 mm/tip for MeteoRain).
- Geographic/radius station selection and a map picker.
- German translation of UI strings (structure ready; strings only in English for
  v1).

## 14. References

- API reference (unofficial): `maxliesegang/ka-sensorcity-explorer` →
  `karlsruhe_sensorcity_api.md`.
- Dashboard: `https://geoportal.karlsruhe.de/sensorcity/Dashboard/`.
- ArcGIS REST query docs:
  `https://developers.arcgis.com/rest/services-reference/enterprise/query-feature-service-layer/`.
- HA integration docs: `https://developers.home-assistant.io/docs/creating_component_index/`.
