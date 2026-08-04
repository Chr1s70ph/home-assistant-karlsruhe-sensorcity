"""Tests for the SensorCity data update coordinator."""
import json
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.karlsruhe_sensorcity.const import LAYER_ARCHIVE, LAYER_LIVE
from custom_components.karlsruhe_sensorcity.coordinator import (
    SensorCityDataUpdateCoordinator,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text())


class FakeClient:
    def __init__(self, layer_to_features):
        self._layers = layer_to_features
        self.archive_calls = 0

    async def query(self, layer, where="1=1", out_fields="*", order_by_fields=None, result_record_count=None, return_geometry=False):
        if layer == LAYER_ARCHIVE:
            self.archive_calls += 1
        return self._layers.get(layer, [])


@pytest.mark.asyncio
async def test_update_filters_to_selected(hass: HomeAssistant):
    temp = load("temp_station.json")["features"][0]
    soil = load("soil_station.json")["features"][0]
    client = FakeClient({LAYER_LIVE: [temp, soil], LAYER_ARCHIVE: []})
    coord = SensorCityDataUpdateCoordinator(
        hass, client, [temp["attributes"]["device_id"]], 5
    )
    data = await coord._async_update_data()
    assert set(data.keys()) == {temp["attributes"]["device_id"]}


@pytest.mark.asyncio
async def test_update_enriches_weather_with_archive(hass: HomeAssistant):
    temp = load("temp_station.json")["features"][0]
    dev = temp["attributes"]["device_id"]
    archive = load("temp_station_archive.json")["features"][0]
    client = FakeClient({LAYER_LIVE: [temp], LAYER_ARCHIVE: [archive]})
    coord = SensorCityDataUpdateCoordinator(hass, client, [dev], 5)
    data = await coord._async_update_data()
    st = data[dev]
    assert st.raw.get("niederschlag") == archive["attributes"]["niederschlag"]
    assert client.archive_calls == 1


@pytest.mark.asyncio
async def test_update_does_not_enrich_non_weather(hass: HomeAssistant):
    soil = load("soil_station.json")["features"][0]
    dev = soil["attributes"]["device_id"]
    client = FakeClient({LAYER_LIVE: [soil], LAYER_ARCHIVE: []})
    coord = SensorCityDataUpdateCoordinator(hass, client, [dev], 5)
    await coord._async_update_data()
    assert client.archive_calls == 0


@pytest.mark.asyncio
async def test_update_raises_update_failed_on_error(hass: HomeAssistant):
    class BoomClient:
        async def query(self, *a, **k):
            raise RuntimeError("boom")
    coord = SensorCityDataUpdateCoordinator(hass, BoomClient(), ["x"], 5)
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()


@pytest.mark.asyncio
async def test_update_empty_when_no_selected_match(hass: HomeAssistant):
    client = FakeClient({LAYER_LIVE: []})
    coord = SensorCityDataUpdateCoordinator(hass, client, ["nonexistent"], 5)
    data = await coord._async_update_data()
    assert data == {}
