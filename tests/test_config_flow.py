"""Tests for config and options flows."""
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.karlsruhe_sensorcity import config_flow
from custom_components.karlsruhe_sensorcity.const import (
    CONF_SCAN_INTERVAL,
    CONF_STATIONS,
    DOMAIN,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text())


def fields_of(schema):
    return {getattr(k, "schema", k) for k in schema.schema}


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
    assert result["type"] == FlowResultType.FORM
    assert "stations" in fields_of(result["data_schema"])


@pytest.mark.asyncio
async def test_user_step_empty_selection_errors(hass):
    flow = config_flow.KarlsruheSensorCityConfigFlow()
    flow.hass = hass
    with patch.object(config_flow, "fetch_all_stations", new=AsyncMock(return_value=features_all())):
        result = await flow.async_step_user({"stations": []})
    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["stations"] == "select_one"


@pytest.mark.asyncio
async def test_user_step_creates_entry(hass):
    flow = config_flow.KarlsruheSensorCityConfigFlow()
    flow.hass = hass
    dev = load("temp_station.json")["features"][0]["attributes"]["device_id"]
    with patch.object(config_flow, "fetch_all_stations", new=AsyncMock(return_value=features_all())):
        result = await flow.async_step_user({"stations": [dev]})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Karlsruhe SensorCity"
    assert result["data"][CONF_STATIONS] == [dev]


@pytest.mark.asyncio
async def test_options_flow_shows_form_prefilled(hass):
    dev = load("temp_station.json")["features"][0]["attributes"]["device_id"]
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_STATIONS: [dev]},
        options={CONF_SCAN_INTERVAL: 5},
        entry_id="test-entry",
    )
    entry.add_to_hass(hass)
    flow = config_flow.KarlsruheSensorCityOptionsFlow()
    flow.handler = "test-entry"
    flow.hass = hass
    with patch.object(config_flow, "fetch_all_stations", new=AsyncMock(return_value=features_all())):
        result = await flow.async_step_init(None)
    assert result["type"] == FlowResultType.FORM
    assert "stations" in fields_of(result["data_schema"])
    assert "scan_interval" in fields_of(result["data_schema"])


@pytest.mark.asyncio
async def test_options_flow_empty_selection_errors(hass):
    dev = load("temp_station.json")["features"][0]["attributes"]["device_id"]
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_STATIONS: [dev]},
        options={CONF_SCAN_INTERVAL: 5},
        entry_id="test-entry",
    )
    entry.add_to_hass(hass)
    flow = config_flow.KarlsruheSensorCityOptionsFlow()
    flow.handler = "test-entry"
    flow.hass = hass
    with patch.object(config_flow, "fetch_all_stations", new=AsyncMock(return_value=features_all())):
        result = await flow.async_step_init({CONF_STATIONS: [], CONF_SCAN_INTERVAL: 10})
    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["stations"] == "select_one"
