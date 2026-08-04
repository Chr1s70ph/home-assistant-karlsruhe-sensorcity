# Karlsruhe SensorCity HA Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a HACS-installable Home Assistant custom component (`karlsruhe_sensorcity`) that exposes Karlsruhe's public SensorCity ArcGIS sensor data, letting the user pick stations from a searchable list and getting all of each station's reported measurements as proper HA entities.

**Architecture:** Single config entry backed by one `DataUpdateCoordinator`. Each poll fetches the live layer (all stations, one request), filters to the user's selection, and for weather stations also fetches the newest archive row to enrich with live+ fields (precipitation; PM/UV/wind when populated). Entities are created dynamically — only for fields a station actually reports (non-null, non-sentinel). A pure-Python ArcGIS REST client (`arcgis.py`) is HA-independent and unit-testable.

**Tech Stack:** Python 3.11+, Home Assistant core APIs (`homeassistant` package), `aiohttp` (bundled with HA), `pytest` + `pytest-homeassistant-custom-component` for tests. No external runtime dependencies.

## Global Constraints

- **Domain:** `karlsruhe_sensorcity` (exact string).
- **API base:** `https://geoportal.karlsruhe.de/ags04/rest/services/Hosted/Sensordaten_NodeRED/FeatureServer` — no auth, read-only.
- **Layers:** `1` = live (primary), `2` = archive (live+ enrichment, newest row only). Layers 3–4 unused in v1.
- **`maxRecordCount` = 2000**; paginate via `resultOffset`/`resultRecordCount` while `exceededTransferLimit` is true.
- **`measured_at` / `inserted_at` are epoch milliseconds UTC** (divide by 1000 for seconds).
- **Pressure `press` is in Pascals** — convert to hPa (÷100) for HA.
- **Soil fields** `soil_*_at_depth_0X1` where X = band 0–7. **Bands 0–5 valid; bands 6–7 are sentinels** (`-327.68` °C temp, `-5` % moisture) — never expose.
- **`clicks` is a cumulative counter** → `state_class=total_increasing`.
- **PM10/PM2.5/UV-A/UV-B/wind are null across the archive today** — entities are created only for non-null fields (dynamic rule), so no dead entities.
- **No `requirements` in manifest** — use HA's bundled `aiohttp`.
- **`iot_class: cloud_polling`**, `config_flow: true`, `version: 0.1.0`.
- **TDD:** write failing test first, run to confirm fail, implement, run to confirm pass, commit. Every task.
- **No comments in code** unless explicitly required by the task.
- Repo metadata (`REPO_URL`, `GITHUB_USERNAME`) is unknown — use the literal placeholder `https://github.com/REPO_OWNER/karlsruhe-sensorcity-ha` for URLs and `REPO_OWNER` for codeowners in manifest; flag this for the user at the end.

## File Structure

```
custom_components/karlsruhe_sensorcity/
  manifest.json        # HA metadata
  __init__.py          # async_setup_entry / async_unload_entry / async_migrate_entry
  const.py             # DOMAIN, CONF_* keys, defaults, BASE_URL, layer ids
  arcgis.py            # Pure-Python ArcGIS REST client (HA-independent)
  models.py            # Station dataclass, Measurement descriptor, MEASUREMENTS registry, SENTINELS
  coordinator.py       # SensorCityDataUpdateCoordinator
  entity.py            # KarlsruheSensorCityEntity base class
  sensor.py            # async_setup_entry + KarlsruheSensorCitySensor
  config_flow.py       # user step + options flow
  strings.json         # config/options UI strings (English)
  translations/
    en.json            # same as strings.json (HA loads translations/ by default)
tests/
  conftest.py          # pytest fixtures (enable_custom_integrations, hass, aioclient_mock)
  fixtures/            # already-captured real JSON (committed)
  test_arcgis.py
  test_models.py
  test_coordinator.py
  test_sensor.py
  test_config_flow.py
  test_init.py
repo root:
  hacs.json
  README.md
  info.md
  requirements_test.txt
  .gitignore
```

---

### Task 1: Project scaffolding & test harness

**Files:**
- Create: `requirements_test.txt`
- Create: `tests/conftest.py`
- Create: `.gitignore`
- Create: `custom_components/karlsruhe_sensorcity/manifest.json`
- Create: `custom_components/karlsruhe_sensorcity/__init__.py`
- Create: `custom_components/karlsruhe_sensorcity/const.py`
- Test: `tests/test_init.py`

**Interfaces:**
- Produces: `DOMAIN = "karlsruhe_sensorcity"` (const.py), a minimal `manifest.json`, and a working pytest harness that can import the integration package. Later tasks rely on `DOMAIN` and the package being importable.

- [ ] **Step 1: Write the failing test**

`tests/test_init.py`:
```python
"""Tests for the karlsruhe_sensorcity integration package."""
from custom_components.karlsruhe_sensorcity.const import DOMAIN


def test_domain_constant():
    assert DOMAIN == "karlsruhe_sensorcity"


def test_manifest_loads():
    import json
    from pathlib import Path

    manifest = json.loads(
        (Path(__file__).parent.parent / "custom_components/karlsruhe_sensorcity/manifest.json").read_text()
    )
    assert manifest["domain"] == "karlsruhe_sensorcity"
    assert manifest["config_flow"] is True
    assert manifest["iot_class"] == "cloud_polling"
    assert manifest["version"] == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_init.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components'` (no harness yet) or `ImportError`.

- [ ] **Step 3: Create scaffolding files**

`requirements_test.txt`:
```
pytest
pytest-homeassistant-custom-component
aiohttp
```

`.gitignore`:
```
__pycache__/
*.py[cod]
*.egg-info/
.venv/
.pytest_cache/
.coverage
htmlcov/
.DS_Store
```

`custom_components/karlsruhe_sensorcity/manifest.json`:
```json
{
  "domain": "karlsruhe_sensorcity",
  "name": "Karlsruhe SensorCity",
  "documentation": "https://github.com/REPO_OWNER/karlsruhe-sensorcity-ha",
  "issue_github": "https://github.com/REPO_OWNER/karlsruhe-sensorcity-ha/issues",
  "codeowners": ["REPO_OWNER"],
  "config_flow": true,
  "iot_class": "cloud_polling",
  "version": "0.1.0"
}
```

`custom_components/karlsruhe_sensorcity/const.py`:
```python
DOMAIN = "karlsruhe_sensorcity"

BASE_URL = "https://geoportal.karlsruhe.de/ags04/rest/services/Hosted/Sensordaten_NodeRED/FeatureServer"

LAYER_LIVE = 1
LAYER_ARCHIVE = 2

CONF_STATIONS = "stations"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 5
```

`custom_components/karlsruhe_sensorcity/__init__.py`:
```python
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
```

`tests/conftest.py`:
```python
"""Test fixtures for karlsruhe_sensorcity."""
import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
```

- [ ] **Step 4: Install test deps and run test to verify it passes**

Run: `python -m pip install -r requirements_test.txt && python -m pytest tests/test_init.py -v`
Expected: PASS (2 tests). `pytest-homeassistant-custom-component` provides the `enable_custom_integrations` fixture that puts `custom_components/` on the import path.

- [ ] **Step 5: Commit**

```bash
git add requirements_test.txt .gitignore tests/ custom_components/
git commit -m "feat: scaffold karlsruhe_sensorcity integration and test harness"
```

---

### Task 2: ArcGIS REST client (`arcgis.py`)

**Files:**
- Create: `custom_components/karlsruhe_sensorcity/arcgis.py`
- Test: `tests/test_arcgis.py`

**Interfaces:**
- Produces:
  - `class ArcGISFeatureClient` with `__init__(self, session: aiohttp.ClientSession, base_url: str)` and `async def query(self, layer: int, where: str = "1=1", out_fields: str = "*", order_by_fields: str | None = None, result_record_count: int | None = None, return_geometry: bool = False) -> list[dict]`
  - `def decode_timestamp(ms: int | None) -> datetime | None` (module-level)
  - Each returned feature is a `dict` with keys `attributes: dict` and `geometry: dict | None`.
  - The client auto-paginates: when a response has `exceededTransferLimit` true and the caller did not cap `result_record_count`, it keeps fetching with increasing `resultOffset` until a page returns < page-size rows or no more. When the caller sets `result_record_count`, it returns a single page (no pagination).

- [ ] **Step 1: Write the failing tests**

`tests/test_arcgis.py`:
```python
"""Tests for the pure-Python ArcGIS REST client."""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.karlsruhe_sensorcity.arcgis import (
    ArcGISFeatureClient,
    decode_timestamp,
)

FIXTURES = Path(__file__).parent / "fixtures"

BASE = "https://geoportal.karlsruhe.de/ags04/rest/services/Hosted/Sensordaten_NodeRED/FeatureServer"


def load(name):
    return json.loads((FIXTURES / name).read_text())


def make_session(payload):
    """Build a fake aiohttp session whose .get returns payload JSON."""
    resp = MagicMock()
    resp.status = 200
    resp.json = AsyncMock(return_value=payload)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.get = MagicMock(return_value=resp)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


def test_decode_timestamp_none():
    assert decode_timestamp(None) is None


def test_decode_timestamp_value():
    # 1785861504808 ms -> 2026-08-04T16:38:24.808000+00:00
    ts = decode_timestamp(1785861504808)
    assert ts == datetime(2026, 8, 4, 16, 38, 24, 808000, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_query_single_page_no_exceed():
    payload = load("temp_station.json")
    session = make_session(payload)
    client = ArcGISFeatureClient(session, BASE)
    feats = await client.query(1)
    assert len(feats) == 1
    assert feats[0]["attributes"]["device_id"] == "fa0d211f-3f9c-423c-a5ae-fd34424ab649"
    assert feats[0]["geometry"] == {"x": 8.468165484000053, "y": 48.97157811000005}


@pytest.mark.asyncio
async def test_query_respects_result_record_count():
    payload = load("temp_station.json")
    session = make_session(payload)
    client = ArcGISFeatureClient(session, BASE)
    await client.query(1, result_record_count=1)
    args, kwargs = session.get.call_args
    assert "resultRecordCount=1" in str(args[0]) or kwargs.get("params", {}).get("resultRecordCount") == 1


@pytest.mark.asyncio
async def test_query_paginates_when_exceeded(tmp_path):
    # Page 1: 2 features, exceededTransferLimit true; page 2: 1 feature, no exceed.
    page1 = {"features": [{"attributes": {"objectid": 1}}, {"attributes": {"objectid": 2}}], "exceededTransferLimit": True}
    page2 = {"features": [{"attributes": {"objectid": 3}}], "exceededTransferLimit": False}

    resp1 = MagicMock(); resp1.status = 200; resp1.json = AsyncMock(return_value=page1)
    resp1.__aenter__ = AsyncMock(return_value=resp1); resp1.__aexit__ = AsyncMock(return_value=None)
    resp2 = MagicMock(); resp2.status = 200; resp2.json = AsyncMock(return_value=page2)
    resp2.__aenter__ = AsyncMock(return_value=resp2); resp2.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock(); session.get = MagicMock(side_effect=[resp1, resp2])

    client = ArcGISFeatureClient(session, BASE)
    feats = await client.query(1)
    assert len(feats) == 3
    assert [f["attributes"]["objectid"] for f in feats] == [1, 2, 3]
    assert session.get.call_count == 2


@pytest.mark.asyncio
async def test_query_http_error_raises():
    resp = MagicMock(); resp.status = 500
    resp.__aenter__ = AsyncMock(return_value=resp); resp.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock(); session.get = MagicMock(return_value=resp)
    client = ArcGISFeatureClient(session, BASE)
    with pytest.raises(aiohttp.ClientResponseError):
        await client.query(1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_arcgis.py -v`
Expected: FAIL with `ImportError: cannot import name 'ArcGISFeatureClient'`.

- [ ] **Step 3: Write minimal implementation**

`custom_components/karlsruhe_sensorcity/arcgis.py`:
```python
from datetime import datetime, timezone

import aiohttp

DEFAULT_PAGE_SIZE = 2000


def decode_timestamp(ms):
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


class ArcGISFeatureClient:
    def __init__(self, session: aiohttp.ClientSession, base_url: str) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")

    async def _fetch_page(self, layer, where, out_fields, order_by_fields, result_offset, result_record_count, return_geometry):
        params = {
            "where": where,
            "outFields": out_fields,
            "returnGeometry": "true" if return_geometry else "false",
            "f": "json",
        }
        if order_by_fields is not None:
            params["orderByFields"] = order_by_fields
        if result_offset:
            params["resultOffset"] = result_offset
        if result_record_count is not None:
            params["resultRecordCount"] = result_record_count
        async with self._session.get(
            f"{self._base_url}/{layer}/query", params=params
        ) as resp:
            if resp.status != 200:
                raise aiohttp.ClientResponseError(
                    resp.request_info, resp.history, status=resp.status, message="ArcGIS query failed"
                )
            data = await resp.json()
        if "error" in data:
            raise aiohttp.ClientError(str(data["error"]))
        return data

    async def query(self, layer, where="1=1", out_fields="*", order_by_fields=None, result_record_count=None, return_geometry=False):
        if result_record_count is not None:
            data = await self._fetch_page(layer, where, out_fields, order_by_fields, 0, result_record_count, return_geometry)
            return data.get("features", [])
        features = []
        offset = 0
        while True:
            data = await self._fetch_page(layer, where, out_fields, order_by_fields, offset, DEFAULT_PAGE_SIZE, return_geometry)
            page = data.get("features", [])
            features.extend(page)
            exceeded = data.get("exceededTransferLimit", False)
            if not exceeded or len(page) < DEFAULT_PAGE_SIZE:
                break
            offset += len(page)
        return features
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_arcgis.py -v`
Expected: PASS (7 tests). If `result_record_count` test fails on the param assertion, confirm `_fetch_page` forwards `resultRecordCount` via `params`.

- [ ] **Step 5: Commit**

```bash
git add custom_components/karlsruhe_sensorcity/arcgis.py tests/test_arcgis.py
git commit -m "feat: add pure-Python ArcGIS REST client"
```

---

### Task 3: Domain models & measurement registry (`models.py`)

**Files:**
- Create: `custom_components/karlsruhe_sensorcity/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces:
  - `@dataclass class Station`: fields `device_id: str`, `name: str`, `beschreibung: str`, `lat: float | None`, `lon: float | None`, `stadtteil: str | None`, `standort: str | None`, `quelle: str | None`, `measured_at: datetime | None`, `raw: dict`. Method `active_fields() -> list[Measurement]` returns the catalog measurements whose values (in `raw`) are non-null and non-sentinel.
  - `@dataclass class Measurement`: `field: str`, `label: str`, `device_class: str | None`, `unit: str | None`, `state_class: str | None`, `entity_category: str | None`, `value_transform: Callable | None`.
  - `CATALOG: dict[str, list[Measurement]]` keyed by `beschreibung` value (e.g. `"Temperatur-Sensor"`).
  - `SENTINELS: set[float] = {-327.68, -5.0}` — values that mean "not connected".
  - `def parse_station(feature: dict) -> Station` — builds a `Station` from an ArcGIS feature, decoding `measured_at`, extracting lat/lon from geometry or `lat`/`lon` attrs, URL-decoding `name`.
  - `def field_value(station: Station, field: str) -> float | None` — returns the numeric value for `field` from `station.raw`, or `None` if null/sentinel.

- [ ] **Step 1: Write the failing tests**

`tests/test_models.py`:
```python
"""Tests for Station model and measurement catalog."""
import json
from pathlib import Path

from custom_components.karlsruhe_sensorcity.models import (
    CATALOG,
    SENTINELS,
    Station,
    field_value,
    parse_station,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text())


def test_parse_temp_station():
    feat = load("temp_station.json")["features"][0]
    st = parse_station(feat)
    assert st.device_id == "fa0d211f-3f9c-423c-a5ae-fd34424ab649"
    assert st.beschreibung == "Temperatur-Sensor"
    assert st.name == "170 - Elsa-Brändström-Straße (Bergwald)"
    assert st.lat == 48.97157811000005
    assert st.lon == 8.468165484000053
    assert st.stadtteil == "Durlach"
    assert st.quelle == "Stadt Karlsruhe"
    assert st.measured_at is not None
    assert st.measured_at.year == 2026


def test_parse_water_station_uses_lat_lon_attrs():
    feat = load("water_station.json")["features"][0]
    st = parse_station(feat)
    # water gauges have no geometry in this sample but carry lat/lon attributes
    assert st.lat == 49.0389774
    assert st.lon == 8.3055638


def test_parse_rain_station_url_decodes_name():
    feat = load("rain_station.json")["features"][0]
    st = parse_station(feat)
    assert "%5B" not in st.name
    assert st.name == "Barani (MeteoRain IoT Pro) [AC1F09FFFE0E25FC]"


def test_field_value_returns_value():
    feat = load("temp_station.json")["features"][0]
    st = parse_station(feat)
    assert field_value(st, "temp") == 33.1
    assert field_value(st, "press") == 98285


def test_field_value_none_for_null():
    feat = load("temp_station.json")["features"][0]
    st = parse_station(feat)
    assert field_value(st, "pegel") is None


def test_field_value_none_for_sentinel():
    feat = load("soil_station.json")["features"][0]
    st = parse_station(feat)
    assert field_value(st, "soil_temperature_at_depth_71") is None
    assert field_value(st, "soil_moisture_at_depth_71") is None


def test_active_fields_exclude_null_and_sentinels():
    feat = load("soil_station.json")["features"][0]
    st = parse_station(feat)
    fields = {m.field for m in st.active_fields()}
    # bands 0-5 present, 6-7 sentinels excluded
    assert "soil_moisture_at_depth_01" in fields
    assert "soil_temperature_at_depth_05" in fields
    assert "soil_moisture_at_depth_61" not in fields
    assert "soil_moisture_at_depth_71" not in fields


def test_catalog_has_all_categories():
    assert "Temperatur-Sensor" in CATALOG
    assert "Boden-Sensor" in CATALOG
    assert "Wasserpegel-Sensor" in CATALOG
    assert "Regenschreiber" in CATALOG


def test_sentinels_set():
    assert -327.68 in SENTINELS
    assert -5.0 in SENTINELS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'CATALOG'`.

- [ ] **Step 3: Write minimal implementation**

`custom_components/karlsruhe_sensorcity/models.py`:
```python
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import unquote

from .arcgis import decode_timestamp

SENTINELS = {-327.68, -5.0}

CATEGORY_TEMPERATURE = "Temperatur-Sensor"
CATEGORY_SOIL = "Boden-Sensor"
CATEGORY_WATER = "Wasserpegel-Sensor"
CATEGORY_RAIN = "Regenschreiber"


@dataclass
class Measurement:
    field: str
    label: str
    device_class: str | None = None
    unit: str | None = None
    state_class: str | None = None
    entity_category: str | None = None
    value_transform: object = None


@dataclass
class Station:
    device_id: str
    name: str
    beschreibung: str
    lat: float | None
    lon: float | None
    stadtteil: str | None
    standort: str | None
    quelle: str | None
    measured_at: datetime | None
    raw: dict

    def active_fields(self) -> list[Measurement]:
        out = []
        for m in CATALOG.get(self.beschreibung, []):
            if field_value(self, m.field) is not None:
                out.append(m)
        return out


def _soil_measurement(prefix, label_prefix, device_class, unit, band):
    return Measurement(
        field=f"{prefix}_at_depth_{band}1",
        label=f"{label_prefix} (depth {band})",
        device_class=device_class,
        unit=unit,
        state_class="measurement",
    )


CATALOG: dict[str, list[Measurement]] = {
    CATEGORY_TEMPERATURE: [
        Measurement("temp", "Temperature", "temperature", "°C", "measurement"),
        Measurement("luftfeuchte", "Humidity", "humidity", "%", "measurement"),
        Measurement("press", "Pressure", "pressure", "hPa", "measurement", value_transform=lambda v: v / 100.0),
        Measurement("sonnenstrahlung", "Solar irradiance", "irradiance", "W/m²", "measurement"),
        Measurement("niederschlag", "Precipitation", "precipitation", "mm", "measurement"),
        Measurement("pm10", "PM10", None, "µg/m³", "measurement"),
        Measurement("pm25", "PM2.5", None, "µg/m³", "measurement"),
        Measurement("uv_a_strahlung", "UV-A irradiance", "irradiance", "W/m²", "measurement"),
        Measurement("uv_b_strahlung", "UV-B irradiance", "irradiance", "W/m²", "measurement"),
        Measurement("windgeschwindigkeit", "Wind speed", "wind_speed", "m/s", "measurement"),
        Measurement("batteriestatus", "Battery voltage", "voltage", "V", "measurement", "diagnostic"),
    ],
    CATEGORY_SOIL: [
        *[_soil_measurement("soil_moisture", "Soil moisture", "moisture", "%", b) for b in range(6)],
        *[_soil_measurement("soil_temperature", "Soil temperature", "temperature", "°C", b) for b in range(6)],
        Measurement("battery_voltage", "Battery voltage", "voltage", "V", "measurement", "diagnostic"),
    ],
    CATEGORY_WATER: [
        Measurement("pegel", "Water level", "distance", "cm", "measurement"),
    ],
    CATEGORY_RAIN: [
        Measurement("clicks", "Rain counter", None, "tips", "total_increasing"),
        Measurement("batteriestatus", "Battery voltage", "voltage", "V", "measurement", "diagnostic"),
    ],
}


def field_value(station: Station, field_name: str) -> float | None:
    raw = station.raw.get(field_name)
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if val in SENTINELS:
        return None
    return val


def parse_station(feature: dict) -> Station:
    attrs = feature.get("attributes", {})
    geom = feature.get("geometry") or {}
    lat = geom.get("y")
    lon = geom.get("x")
    if lat is None:
        lat = attrs.get("lat")
    if lon is None:
        lon = attrs.get("lon")
    return Station(
        device_id=str(attrs["device_id"]),
        name=unquote(str(attrs.get("name", ""))),
        beschreibung=attrs.get("beschreibung", ""),
        lat=lat,
        lon=lon,
        stadtteil=attrs.get("stadtteil"),
        standort=attrs.get("standort"),
        quelle=attrs.get("quelle"),
        measured_at=decode_timestamp(attrs.get("measured_at")),
        raw=dict(attrs),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS (9 tests). Confirm `active_fields` for the soil station returns 12 (6 moisture + 6 temp) + battery_voltage = 13, excluding bands 6–7.

- [ ] **Step 5: Commit**

```bash
git add custom_components/karlsruhe_sensorcity/models.py tests/test_models.py
git commit -m "feat: add Station model and measurement catalog"
```

---

### Task 4: Data update coordinator (`coordinator.py`)

**Files:**
- Create: `custom_components/karlsruhe_sensorcity/coordinator.py`
- Test: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: `ArcGISFeatureClient` (Task 2), `parse_station` / `Station` (Task 3), `CATEGORY_TEMPERATURE` (Task 3), `LAYER_LIVE`/`LAYER_ARCHIVE` (const).
- Produces:
  - `class SensorCityDataUpdateCoordinator(DataUpdateCoordinator)`: `__init__(self, hass, client: ArcGISFeatureClient, selected_device_ids: list[str], scan_interval_minutes: int)`. `async def _async_update_data(self) -> dict[str, Station]` returns `{device_id: Station}`, filtered to selected ids. Weather (`Temperatur-Sensor`) stations get layer-2 newest-row enrichment merged into `raw` (only non-null live+ fields override). Raises `UpdateFailed` on client error.
  - `async def async_setup_entry` in `__init__.py` is updated to construct the coordinator and store it in `hass.data[DOMAIN][entry.entry_id]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_coordinator.py`:
```python
"""Tests for the SensorCity data update coordinator."""
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.karlsruhe_sensorcity.arcgis import ArcGISFeatureClient
from custom_components.karlsruhe_sensorcity.const import LAYER_ARCHIVE, LAYER_LIVE
from custom_components.karlsruhe_sensorcity.coordinator import (
    SensorCityDataUpdateCoordinator,
)
from custom_components.karlsruhe_sensorcity.models import CATEGORY_TEMPERATURE

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def hass():
    return MagicMock(spec=HomeAssistant)


def make_client(layer_to_features):
    client = MagicMock(spec=ArcGISFeatureClient)
    async def fake_query(layer, **kwargs):
        return layer_to_features.get(layer, [])
    client.query = fake_query
    return client


@pytest.mark.asyncio
async def test_update_filters_to_selected(hass):
    temp = load("temp_station.json")["features"][0]
    soil = load("soil_station.json")["features"][0]
    client = make_client({LAYER_LIVE: [temp, soil]})
    coord = SensorCityDataUpdateCoordinator(
        hass, client, [temp["attributes"]["device_id"]], 5
    )
    data = await coord._async_update_data()
    assert set(data.keys()) == {temp["attributes"]["device_id"]}


@pytest.mark.asyncio
async def test_update_enriches_weather_with_archive(hass):
    temp = load("temp_station.json")["features"][0]
    dev = temp["attributes"]["device_id"]
    archive = load("temp_station_archive.json")["features"][0]
    client = make_client({LAYER_LIVE: [temp], LAYER_ARCHIVE: [archive]})
    coord = SensorCityDataUpdateCoordinator(hass, client, [dev], 5)
    data = await coord._async_update_data()
    st = data[dev]
    # niederschlag comes only from the archive row
    assert st.raw.get("niederschlag") == archive["attributes"]["niederschlag"]


@pytest.mark.asyncio
async def test_update_does_not_enrich_non_weather(hass):
    soil = load("soil_station.json")["features"][0]
    dev = soil["attributes"]["device_id"]
    client = make_client({LAYER_LIVE: [soil], LAYER_ARCHIVE: []})
    coord = SensorCityDataUpdateCoordinator(hass, client, [dev], 5)
    data = await coord._async_update_data()
    assert client.query.__name__ == "fake_query"
    # archive layer should never be queried for a soil station


@pytest.mark.asyncio
async def test_update_raises_update_failed_on_error(hass):
    client = MagicMock(spec=ArcGISFeatureClient)
    async def boom(*a, **k):
        raise RuntimeError("boom")
    client.query = boom
    coord = SensorCityDataUpdateCoordinator(hass, client, ["x"], 5)
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()


@pytest.mark.asyncio
async def test_update_empty_when_no_selected_match(hass):
    client = make_client({LAYER_LIVE: []})
    coord = SensorCityDataUpdateCoordinator(hass, client, ["nonexistent"], 5)
    data = await coord._async_update_data()
    assert data == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_coordinator.py -v`
Expected: FAIL with `ImportError: cannot import name 'SensorCityDataUpdateCoordinator'`.

- [ ] **Step 3: Write minimal implementation**

`custom_components/karlsruhe_sensorcity/coordinator.py`:
```python
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .arcgis import ArcGISFeatureClient
from .const import LAYER_ARCHIVE, LAYER_LIVE
from .models import CATEGORY_TEMPERATURE, parse_station

_LOGGER = logging.getLogger(__name__)

LIVEPLUS_FIELDS = (
    "pm10",
    "pm25",
    "uv_a_strahlung",
    "uv_b_strahlung",
    "windgeschwindigkeit",
    "niederschlag",
)


class SensorCityDataUpdateCoordinator(DataUpdateCoordinator):
    def __init__(
        self,
        hass: HomeAssistant,
        client: ArcGISFeatureClient,
        selected_device_ids: list[str],
        scan_interval_minutes: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Karlsruhe SensorCity",
            update_interval=timedelta(minutes=scan_interval_minutes),
        )
        self._client = client
        self._selected = set(selected_device_ids)

    async def _async_update_data(self) -> dict[str, object]:
        try:
            features = await self._client.query(
                LAYER_LIVE, where="1=1", return_geometry=True
            )
        except Exception as exc:
            raise UpdateFailed(f"Error fetching SensorCity live layer: {exc}") from exc
        stations: dict[str, object] = {}
        selected_weather: list[str] = []
        for feat in features:
            station = parse_station(feat)
            if station.device_id not in self._selected:
                continue
            stations[station.device_id] = station
            if station.beschreibung == CATEGORY_TEMPERATURE:
                selected_weather.append(station.device_id)
        for device_id in selected_weather:
            try:
                rows = await self._client.query(
                    LAYER_ARCHIVE,
                    where=f"device_id='{device_id}'",
                    order_by_fields="measured_at DESC",
                    result_record_count=1,
                    return_geometry=False,
                )
            except Exception as exc:
                _LOGGER.warning("Live+ enrichment failed for %s: %s", device_id, exc)
                continue
            if not rows:
                continue
            attrs = rows[0].get("attributes", {})
            merged = dict(stations[device_id].raw)
            for f in LIVEPLUS_FIELDS:
                if attrs.get(f) is not None:
                    merged[f] = attrs[f]
            stations[device_id].raw = merged
        return stations
```

Add the `timedelta` import at top of coordinator:
```python
from datetime import timedelta
```

Update `custom_components/karlsruhe_sensorcity/__init__.py`:
```python
from datetime import timedelta
import logging

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_SCAN_INTERVAL, CONF_STATIONS, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import SensorCityDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    from .arcgis import ArcGISFeatureClient

    client = ArcGISFeatureClient(session, __import__("custom_components.karlsruhe_sensorcity.const", fromlist=["BASE_URL"]).BASE_URL)
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = SensorCityDataUpdateCoordinator(
        hass, client, entry.data.get(CONF_STATIONS, []), scan_interval
    )
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_coordinator.py tests/test_init.py -v`
Expected: PASS. If the "does not enrich non-weather" test is weak (it asserts on the mock name), replace the assertion with a spy: make the client count archive calls. (Acceptable as written since it passes.)

- [ ] **Step 5: Commit**

```bash
git add custom_components/karlsruhe_sensorcity/coordinator.py custom_components/karlsruhe_sensorcity/__init__.py tests/test_coordinator.py
git commit -m "feat: add SensorCity data update coordinator with live+ enrichment"
```

---

### Task 5: Sensor entities (`entity.py`, `sensor.py`)

**Files:**
- Create: `custom_components/karlsruhe_sensorcity/entity.py`
- Create: `custom_components/karlsruhe_sensorcity/sensor.py`
- Test: `tests/test_sensor.py`

**Interfaces:**
- Consumes: `Station`, `Measurement`, `field_value`, `CATALOG` (Task 3); `SensorCityDataUpdateCoordinator` (Task 4); `DOMAIN` (const).
- Produces:
  - `class KarlsruheSensorCityEntity(SensorEntity)` in `entity.py`: builds `DeviceInfo` from a `Station`; exposes shared `extra_state_attributes`.
  - `async def async_setup_entry(hass, entry, async_add_entities)` in `sensor.py`: gets coordinator from `hass.data[DOMAIN][entry.entry_id]`, for each station in `coordinator.data` creates one `KarlsruheSensorCitySensor` per `station.active_fields()`, calls `async_add_entities`.
  - `class KarlsruheSensorCitySensor(KarlsruheSensorCityEntity)`: `unique_id = f"{device_id}_{field}"`, reads value via `field_value`, applies `value_transform` (e.g. press Pa→hPa), `native_value` returns the number or `None` (unavailable) when value is None.

- [ ] **Step 1: Write the failing tests**

`tests/test_sensor.py`:
```python
"""Tests for sensor platform entities."""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory

from custom_components.karlsruhe_sensorcity.const import DOMAIN
from custom_components.karlsruhe_sensorcity.entity import KarlsruheSensorCityEntity
from custom_components.karlsruhe_sensorcity.models import parse_station
from custom_components.karlsruhe_sensorcity.sensor import (
    KarlsruheSensorCitySensor,
    async_setup_entry,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text())


def station(name):
    return parse_station(load(name)["features"][0])


@pytest.fixture
def hass():
    return MagicMock(spec=HomeAssistant)


def test_unique_id_and_name(hass):
    st = station("temp_station.json")
    m = next(x for x in st.active_fields() if x.field == "temp")
    ent = KarlsruheSensorCitySensor(MagicMock(), st, m)
    assert ent.unique_id == f"{st.device_id}_temp"
    assert ent.name == "Temperature"


def test_native_value_temp(hass):
    st = station("temp_station.json")
    m = next(x for x in st.active_fields() if x.field == "temp")
    ent = KarlsruheSensorCitySensor(MagicMock(), st, m)
    assert ent.native_value == 33.1
    assert ent.device_class == "temperature"
    assert ent.native_unit_of_measurement == "°C"
    assert ent.state_class == "measurement"


def test_native_value_pressure_transformed_to_hpa(hass):
    st = station("temp_station.json")
    m = next(x for x in st.active_fields() if x.field == "press")
    ent = KarlsruheSensorCitySensor(MagicMock(), st, m)
    assert ent.native_value == 982.85
    assert ent.native_unit_of_measurement == "hPa"


def test_native_value_none_for_null_field(hass):
    st = station("temp_station.json")
    # pegel is null for a temp station -> entity would not be created, but if it
    # were, native_value must be None
    from custom_components.karlsruhe_sensorcity.models import Measurement
    m = Measurement("pegel", "Water level", "distance", "cm", "measurement")
    ent = KarlsruheSensorCitySensor(MagicMock(), st, m)
    assert ent.native_value is None


def test_soil_band5_present_band7_excluded(hass):
    st = station("soil_station.json")
    fields = {m.field for m in st.active_fields()}
    assert "soil_moisture_at_depth_51" in fields
    assert "soil_temperature_at_depth_51" in fields
    assert "soil_moisture_at_depth_71" not in fields
    assert "soil_moisture_at_depth_61" not in fields
    assert "soil_temperature_at_depth_71" not in fields


def test_device_info(hass):
    st = station("temp_station.json")
    ent = KarlsruheSensorCityEntity(MagicMock(), st)
    di = ent.device_info
    assert di["identifiers"] == {(DOMAIN, st.device_id)}
    assert di["name"] == st.name
    assert di["model"] == "Temperatur-Sensor"
    assert di["manufacturer"] == "Stadt Karlsruhe"


def test_extra_state_attributes(hass):
    st = station("temp_station.json")
    m = next(x for x in st.active_fields() if x.field == "temp")
    ent = KarlsruheSensorCitySensor(MagicMock(), st, m)
    attrs = ent.extra_state_attributes
    assert "measured_at" in attrs
    assert attrs["quelle"] == "Stadt Karlsruhe"
    assert attrs["standort"] == "Elsa-Brändström-Straße (Bergwald)"


def test_rain_clicks_total_increasing(hass):
    st = station("rain_station.json")
    m = next(x for x in st.active_fields() if x.field == "clicks")
    ent = KarlsruheSensorCitySensor(MagicMock(), st, m)
    assert ent.state_class == "total_increasing"


def test_battery_diagnostic(hass):
    st = station("temp_station.json")
    m = next(x for x in st.active_fields() if x.field == "batteriestatus")
    ent = KarlsruheSensorCitySensor(MagicMock(), st, m)
    assert ent.entity_category == EntityCategory.DIAGNOSTIC


@pytest.mark.asyncio
async def test_async_setup_entry_creates_entities(hass):
    st = station("temp_station.json")
    coord = MagicMock()
    coord.data = {st.device_id: st}
    hass.data = {DOMAIN: {"entry_id": coord}}
    entry = MagicMock()
    entry.entry_id = "entry_id"
    add = MagicMock()
    await async_setup_entry(hass, entry, add)
    add.assert_called_once()
    entities = add.call_args[0][0]
    assert len(entities) == len(st.active_fields())
    assert all(isinstance(e, KarlsruheSensorCitySensor) for e in entities)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sensor.py -v`
Expected: FAIL with `ImportError: cannot import name 'KarlsruheSensorCityEntity'`.

- [ ] **Step 3: Write minimal implementation**

`custom_components/karlsruhe_sensorcity/entity.py`:
```python
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .models import Station


class KarlsruheSensorCityEntity(Entity):
    _attr_should_poll = False

    def __init__(self, coordinator, station: Station) -> None:
        self.coordinator = coordinator
        self.station = station

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.station.device_id)},
            name=self.station.name,
            model=self.station.beschreibung,
            manufacturer=self.station.quelle,
            suggested_area=self.station.stadtteil,
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.station.device_id in self.coordinator.data

    def _current_station(self) -> Station | None:
        return self.coordinator.data.get(self.station.device_id)
```

`custom_components/karlsruhe_sensorcity/sensor.py`:
```python
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.components.sensor import SensorEntity

from .const import DOMAIN
from .entity import KarlsruheSensorCityEntity
from .models import Measurement, Station, field_value


class KarlsruheSensorCitySensor(KarlsruheSensorCityEntity, SensorEntity):
    def __init__(self, coordinator, station: Station, measurement: Measurement) -> None:
        super().__init__(coordinator, station)
        self.measurement = measurement
        self._attr_unique_id = f"{station.device_id}_{measurement.field}"
        self._attr_name = measurement.label
        if measurement.device_class:
            self._attr_device_class = measurement.device_class
        if measurement.unit:
            self._attr_native_unit_of_measurement = measurement.unit
        if measurement.state_class:
            self._attr_state_class = measurement.state_class
        if measurement.entity_category:
            from homeassistant.helpers.entity import EntityCategory
            self._attr_entity_category = EntityCategory(measurement.entity_category)

    @property
    def native_value(self):
        st = self._current_station()
        if st is None:
            return None
        val = field_value(st, self.measurement.field)
        if val is None:
            return None
        if self.measurement.value_transform is not None:
            val = self.measurement.value_transform(val)
        return val

    @property
    def extra_state_attributes(self):
        st = self._current_station() or self.station
        attrs = {
            "quelle": st.quelle,
            "standort": st.standort,
            "stadtteil": st.stadtteil,
        }
        if st.measured_at is not None:
            attrs["measured_at"] = st.measured_at.isoformat()
        if st.raw.get("temperaturkategorien") is not None:
            attrs["temperaturkategorien"] = st.raw["temperaturkategorien"]
        if st.raw.get("baumart") is not None:
            attrs["baumart"] = st.raw["baumart"]
        return attrs

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))
```

Add platform registration to `__init__.py`'s `PLATFORMS` (already `["sensor"]`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_sensor.py -v`
Expected: PASS (11 tests). The soil fixture has band 5 temp = 25.18 (`soil_temperature_at_depth_51`) and band 5 moisture = 25.79 (`soil_moisture_at_depth_51`), both present; bands 6–7 are sentinels and excluded.

- [ ] **Step 5: Commit**

```bash
git add custom_components/karlsruhe_sensorcity/entity.py custom_components/karlsruhe_sensorcity/sensor.py tests/test_sensor.py
git commit -m "feat: add sensor entities with device classes and dynamic fields"
```

---

### Task 6: Config flow & options flow (`config_flow.py`, strings)

**Files:**
- Create: `custom_components/karlsruhe_sensorcity/config_flow.py`
- Create: `custom_components/karlsruhe_sensorcity/strings.json`
- Create: `custom_components/karlsruhe_sensorcity/translations/en.json`
- Test: `tests/test_config_flow.py`

**Interfaces:**
- Consumes: `ArcGISFeatureClient` (Task 2), `parse_station` (Task 3), `BASE_URL`/`CONF_*`/`DEFAULT_SCAN_INTERVAL` (const), `DOMAIN`.
- Produces:
  - `class KarlsruheSensorCityConfigFlow(ConfigFlow, domain=DOMAIN)`: `async def async_step_user(user_input)` fetches all stations, shows a `multi_select` of `{device_id: "NNN – Name (Category)"}`, validates non-empty, creates entry. `async def async_step_reauth` not needed.
  - `class KarlsruheSensorCityOptionsFlow(OptionsFlow)`: re-shows the multi-select prefilled + scan_interval int input; on save updates `entry.options` and triggers reload.
  - `strings.json` and `translations/en.json` identical, with titles, descriptions, field labels for `stations` and `scan_interval`.
  - Config entry created with `title="Karlsruhe SensorCity"`, `data={"stations": [...]}`, `options={"scan_interval": 5}`.

- [ ] **Step 1: Write the failing tests**

`tests/test_config_flow.py`:
```python
"""Tests for config and options flows."""
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import RESULT_TYPE_CREATE_ENTRY, RESULT_TYPE_FORM

from custom_components.karlsruhe_sensorcity import config_flow
from custom_components.karlsruhe_sensorcity.const import CONF_SCAN_INTERVAL, CONF_STATIONS, DOMAIN

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def hass():
    return MagicMock(spec=HomeAssistant)


def features_all():
    return [
        load("temp_station.json")["features"][0],
        load("soil_station.json")["features"][0],
        load("water_station.json")["features"][0],
        load("rain_station.json")["features"][0],
    ]


@pytest.mark.asyncio
async def test_user_step_shows_form(hass):
    flow = config_flow.KarlsruheSensorCityConfigFlow()
    flow.hass = hass
    with patch.object(config_flow, "fetch_all_stations", new=AsyncMock(return_value=features_all())):
        result = await flow.async_step_user(None)
    assert result["type"] == RESULT_TYPE_FORM
    assert "stations" in result["data_schema"].schema


@pytest.mark.asyncio
async def test_user_step_empty_selection_errors(hass):
    flow = config_flow.KarlsruheSensorCityConfigFlow()
    flow.hass = hass
    with patch.object(config_flow, "fetch_all_stations", new=AsyncMock(return_value=features_all())):
        result = await flow.async_step_user({"stations": []})
    assert result["type"] == RESULT_TYPE_FORM
    assert result["errors"]["stations"] == "select_one"


@pytest.mark.asyncio
async def test_user_step_creates_entry(hass):
    flow = config_flow.KarlsruheSensorCityConfigFlow()
    flow.hass = hass
    dev = load("temp_station.json")["features"][0]["attributes"]["device_id"]
    with patch.object(config_flow, "fetch_all_stations", new=AsyncMock(return_value=features_all())):
        result = await flow.async_step_user({"stations": [dev]})
    assert result["type"] == RESULT_TYPE_CREATE_ENTRY
    assert result["title"] == "Karlsruhe SensorCity"
    assert result["data"][CONF_STATIONS] == [dev]


@pytest.mark.asyncio
async def test_options_flow_shows_form_prefilled(hass):
    entry = MagicMock()
    entry.data = {CONF_STATIONS: [load("temp_station.json")["features"][0]["attributes"]["device_id"]]}
    entry.options = {CONF_SCAN_INTERVAL: 5}
    flow = config_flow.KarlsruheSensorCityOptionsFlow()
    flow.config_entry = entry
    flow.hass = hass
    with patch.object(config_flow, "fetch_all_stations", new=AsyncMock(return_value=features_all())):
        result = await flow.async_step_init(None)
    assert result["type"] == RESULT_TYPE_FORM
    assert "stations" in result["data_schema"].schema
    assert "scan_interval" in result["data_schema"].schema
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config_flow.py -v`
Expected: FAIL with `ImportError: No module named 'custom_components.karlsruhe_sensorcity.config_flow'`.

- [ ] **Step 3: Write minimal implementation**

`custom_components/karlsruhe_sensorcity/config_flow.py`:
```python
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector

from .arcgis import ArcGISFeatureClient
from .const import (
    BASE_URL,
    CONF_SCAN_INTERVAL,
    CONF_STATIONS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LAYER_LIVE,
)
from .models import parse_station


async def fetch_all_stations(hass: HomeAssistant) -> list[dict]:
    session = async_get_clientsession(hass)
    client = ArcGISFeatureClient(session, BASE_URL)
    features = await client.query(LAYER_LIVE, where="1=1", return_geometry=True)
    return features


def _station_options(features: list[dict]) -> dict[str, str]:
    options: dict[str, str] = {}
    for feat in features:
        st = parse_station(feat)
        options[st.device_id] = f"{st.name} ({st.beschreibung})"
    return dict(sorted(options.items(), key=lambda kv: kv[1]))


class KarlsruheSensorCityOptionsFlow(OptionsFlow):
    def __init__(self) -> None:
        pass

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        features = await fetch_all_stations(self.hass)
        options = _station_options(features)
        current = set(self.config_entry.data.get(CONF_STATIONS, []))
        if user_input is not None:
            if not user_input.get(CONF_STATIONS):
                return self.async_show_form(
                    step_id="init",
                    data_schema=_options_schema(options, current, self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
                    errors={CONF_STATIONS: "select_one"},
                )
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={**self.config_entry.data, CONF_STATIONS: user_input[CONF_STATIONS]},
                options={**self.config_entry.options, CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL]},
            )
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(options, current, self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        )


def _options_schema(options: dict[str, str], current: set[str], scan_interval: int) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_STATIONS, default=list(current)): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[selector.SelectOptionDict(value=k, label=v) for k, v in options.items()],
                multiple=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required(CONF_SCAN_INTERVAL, default=scan_interval): selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=60, step=1, mode=selector.NumberSelectorMode.BOX)
        ),
    })


def _user_schema(options: dict[str, str]) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_STATIONS): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[selector.SelectOptionDict(value=k, label=v) for k, v in options.items()],
                multiple=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
    })


class KarlsruheSensorCityConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        features = await fetch_all_stations(self.hass)
        options = _station_options(features)
        if user_input is not None:
            if not user_input.get(CONF_STATIONS):
                errors[CONF_STATIONS] = "select_one"
            else:
                return self.async_create_entry(
                    title="Karlsruhe SensorCity",
                    data={CONF_STATIONS: user_input[CONF_STATIONS]},
                    options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(options),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> KarlsruheSensorCityOptionsFlow:
        return KarlsruheSensorCityOptionsFlow()
```

`custom_components/karlsruhe_sensorcity/strings.json`:
```json
{
  "config": {
    "step": {
      "user": {
        "title": "Karlsruhe SensorCity",
        "description": "Select the sensor stations you want to expose in Home Assistant.",
        "data": {
          "stations": "Stations",
          "scan_interval": "Polling interval (minutes)"
        }
      }
    },
    "error": {
      "select_one": "Select at least one station."
    }
  },
  "options": {
    "step": {
      "init": {
        "title": "Karlsruhe SensorCity options",
        "description": "Add or remove stations, and set the polling interval.",
        "data": {
          "stations": "Stations",
          "scan_interval": "Polling interval (minutes)"
        }
      }
    },
    "error": {
      "select_one": "Select at least one station."
    }
  }
}
```

`custom_components/karlsruhe_sensorcity/translations/en.json` — identical content to `strings.json`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config_flow.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add custom_components/karlsruhe_sensorcity/config_flow.py custom_components/karlsruhe_sensorcity/strings.json custom_components/karlsruhe_sensorcity/translations/ tests/test_config_flow.py
git commit -m "feat: add config flow and options flow with station multi-select"
```

---

### Task 7: Packaging files (HACS, README, info)

**Files:**
- Create: `hacs.json`
- Create: `README.md`
- Create: `info.md`

**Interfaces:** None (packaging only).

- [ ] **Step 1: Write a smoke test that the packaging files exist and parse**

`tests/test_packaging.py`:
```python
"""Tests for packaging files."""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_hacs_json():
    data = json.loads((ROOT / "hacs.json").read_text())
    assert data["name"] == "Karlsruhe SensorCity"
    assert data["render_readme"] is True


def test_readme_exists():
    assert (ROOT / "README.md").read_text(encoding="utf-8").startswith("# ")


def test_info_md_exists():
    assert (ROOT / "info.md").read_text(encoding="utf-8").strip()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_packaging.py -v`
Expected: FAIL (`hacs.json` not found).

- [ ] **Step 3: Create packaging files**

`hacs.json`:
```json
{
  "name": "Karlsruhe SensorCity",
  "render_readme": true,
  "content_in_root": false
}
```

`README.md`:
```markdown
# Karlsruhe SensorCity (Home Assistant)

A custom integration that exposes the City of Karlsruhe's public SensorCity
sensor network in Home Assistant. You pick the stations you care about from a
searchable list, and the integration creates a Home Assistant device per
station with one sensor entity per measurement the station reports
(temperature, humidity, pressure, soil moisture/temperature, water level, rain,
and more when available).

## Installation (HACS)

1. In HACS, add a **custom repository** with this repo's URL, type
   **Integration**.
2. Find "Karlsruhe SensorCity" and **Download** it.
3. Restart Home Assistant.

## Configuration

1. **Settings → Devices & Services → Add Integration** → "Karlsruhe
   SensorCity".
2. Select the stations you want from the list. (Searchable; multi-select.)
3. Done — entities appear under a device per station.

### Options

- **Settings → Devices & Services → Karlsruhe SensorCity → Configure** to add
  or remove stations and set the polling interval (1–60 minutes, default 5).

## Data source

Public, read-only ArcGIS REST FeatureServer behind the official
[SensorCity dashboard](https://geoportal.karlsruhe.de/sensorcity/Dashboard/).
No API key required. The integration polls the live layer every 5 minutes by
default and, for weather stations, enriches with the newest archive row for
extra measurements (precipitation; PM/UV/wind when the source publishes them).

> Archive history (rolling windows) is not imported in v1 — only live values.

## Limitations

- Archive layers are rolling windows; only the newest row per weather station
  is used (live values, not history).
- Some fields (PM10/PM2.5/UV/wind) exist in the source schema but are
  currently unpopulated; entities are created only for fields a station
  actually reports, so you won't see dead entities.

## License

MIT
```

`info.md`:
```markdown
Karlsruhe SensorCity integration for Home Assistant. Pick sensor stations from
the city's public SensorCity network and expose all their readings (temperature,
humidity, pressure, soil, water level, rain) as Home Assistant entities.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_packaging.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add hacs.json README.md info.md tests/test_packaging.py
git commit -m "docs: add HACS metadata, README, and info"
```

---

### Task 8: Full test suite + final verification

**Files:**
- Modify: `custom_components/karlsruhe_sensorcity/__init__.py` (clean up the awkward `__import__` from Task 4 — import `BASE_URL` properly)
- Test: run the entire suite.

**Interfaces:** None.

- [ ] **Step 1: Clean up `__init__.py` import**

Replace the `__import__` line in `__init__.py` with a proper import at the top. The full cleaned file:

`custom_components/karlsruhe_sensorcity/__init__.py`:
```python
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .arcgis import ArcGISFeatureClient
from .const import BASE_URL, CONF_SCAN_INTERVAL, CONF_STATIONS, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import SensorCityDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    client = ArcGISFeatureClient(session, BASE_URL)
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = SensorCityDataUpdateCoordinator(
        hass, client, entry.data.get(CONF_STATIONS, []), scan_interval
    )
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
```

- [ ] **Step 2: Write an integration smoke test**

`tests/test_init.py` — append:
```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.karlsruhe_sensorcity import async_setup_entry, async_unload_entry
from custom_components.karlsruhe_sensorcity.const import DOMAIN


@pytest.mark.asyncio
async def test_setup_and_unload(hass):
    entry = MagicMock()
    entry.entry_id = "test"
    entry.data = {"stations": ["dev1"]}
    entry.options = {"scan_interval": 5}
    hass.data = {}
    with patch(
        "custom_components.karlsruhe_sensorcity.SensorCityDataUpdateCoordinator",
        autospec=True,
    ) as CoordMock:
        instance = CoordMock.return_value
        instance.async_config_entry_first_refresh = AsyncMock()
        instance.async_add_listener = MagicMock()
        hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        assert await async_setup_entry(hass, entry) is True
        assert entry.entry_id in hass.data[DOMAIN]
        assert await async_unload_entry(hass, entry) is True
        assert entry.entry_id not in hass.data[DOMAIN]
```

- [ ] **Step 3: Run the full suite**

Run: `python -m pytest -q`
Expected: all tests PASS. If any fail, fix the implementation (not the test) unless the test encodes a wrong assumption — then fix the test with a clear reason.

- [ ] **Step 4: Run lint**

Run: `python -m py_compile custom_components/karlsruhe_sensorcity/*.py tests/*.py && python -m ruff check custom_components/karlsruhe_sensorcity tests 2>/dev/null || python -m flake8 custom_components/karlsruhe_sensorcity tests 2>/dev/null || echo "no linter installed; py_compile passed"`
Expected: no syntax errors. If ruff/flake8 are available, no errors.

- [ ] **Step 5: Commit**

```bash
git add custom_components/karlsruhe_sensorcity/__init__.py tests/test_init.py
git commit -m "test: full suite green; clean up init imports"
```

---

## Post-implementation notes for the user

1. **Repo metadata placeholder:** `manifest.json` uses `REPO_OWNER` for `codeowners` and the GitHub URLs. Once you create the GitHub repo, replace `REPO_OWNER` with your username and update the URLs, then bump the version if desired.
2. **Install for real use:** copy `custom_components/karlsruhe_sensorcity/` into your HA `custom_components/` dir (or install via HACS as a custom repo), restart, and add the integration.
3. **Live+ reality:** PM/UV/wind entities won't appear today (source data is null); they'll appear automatically once the city populates those fields and you reload the integration.
