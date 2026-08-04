"""Tests for sensor platform entities."""
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from custom_components.karlsruhe_sensorcity.const import DOMAIN
from custom_components.karlsruhe_sensorcity.entity import KarlsruheSensorCityEntity
from custom_components.karlsruhe_sensorcity.models import Measurement, parse_station
from custom_components.karlsruhe_sensorcity.sensor import (
    KarlsruheSensorCitySensor,
    async_setup_entry,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text())


def station(name):
    return parse_station(load(name)["features"][0])


def make_coord(*stations):
    coord = MagicMock()
    coord.data = {s.device_id: s for s in stations}
    coord.last_update_success = True
    coord.async_add_listener = MagicMock()
    return coord


def test_unique_id_and_name():
    st = station("temp_station.json")
    m = next(x for x in st.active_fields() if x.field == "temp")
    ent = KarlsruheSensorCitySensor(make_coord(st), st, m)
    assert ent.unique_id == f"{st.device_id}_temp"
    assert ent.name == "Temperature"


def test_native_value_temp():
    st = station("temp_station.json")
    m = next(x for x in st.active_fields() if x.field == "temp")
    ent = KarlsruheSensorCitySensor(make_coord(st), st, m)
    assert ent.native_value == 33.1
    assert ent.device_class == "temperature"
    assert ent.native_unit_of_measurement == "°C"
    assert ent.state_class == "measurement"


def test_native_value_pressure_transformed_to_hpa():
    st = station("temp_station.json")
    m = next(x for x in st.active_fields() if x.field == "press")
    ent = KarlsruheSensorCitySensor(make_coord(st), st, m)
    assert ent.native_value == 982.85
    assert ent.native_unit_of_measurement == "hPa"


def test_native_value_none_for_null_field():
    st = station("temp_station.json")
    m = Measurement("pegel", "Water level", "distance", "cm", "measurement")
    ent = KarlsruheSensorCitySensor(make_coord(st), st, m)
    assert ent.native_value is None


def test_soil_band5_present_band7_excluded():
    st = station("soil_station.json")
    fields = {m.field for m in st.active_fields()}
    assert "soil_moisture_at_depth_51" in fields
    assert "soil_temperature_at_depth_51" in fields
    assert "soil_moisture_at_depth_71" not in fields
    assert "soil_moisture_at_depth_61" not in fields
    assert "soil_temperature_at_depth_71" not in fields


def test_device_info():
    st = station("temp_station.json")
    ent = KarlsruheSensorCityEntity(make_coord(st), st)
    di = ent.device_info
    assert di["identifiers"] == {(DOMAIN, st.device_id)}
    assert di["name"] == st.name
    assert di["model"] == "Temperatur-Sensor"
    assert di["manufacturer"] == "Stadt Karlsruhe"


def test_extra_state_attributes():
    st = station("temp_station.json")
    m = next(x for x in st.active_fields() if x.field == "temp")
    ent = KarlsruheSensorCitySensor(make_coord(st), st, m)
    attrs = ent.extra_state_attributes
    assert "measured_at" in attrs
    assert attrs["quelle"] == "Stadt Karlsruhe"
    assert attrs["standort"] == "Elsa-Brändström-Straße (Bergwald)"


def test_rain_clicks_total_increasing():
    st = station("rain_station.json")
    m = next(x for x in st.active_fields() if x.field == "clicks")
    ent = KarlsruheSensorCitySensor(make_coord(st), st, m)
    assert ent.state_class == "total_increasing"


def test_battery_diagnostic():
    st = station("temp_station.json")
    m = next(x for x in st.active_fields() if x.field == "batteriestatus")
    ent = KarlsruheSensorCitySensor(make_coord(st), st, m)
    assert ent.entity_category == EntityCategory.DIAGNOSTIC


@pytest.mark.asyncio
async def test_async_setup_entry_creates_entities(hass: HomeAssistant):
    st = station("temp_station.json")
    coord = make_coord(st)
    hass.data = {DOMAIN: {"entry_id": coord}}
    entry = MagicMock()
    entry.entry_id = "entry_id"
    add = MagicMock()
    await async_setup_entry(hass, entry, add)
    add.assert_called_once()
    entities = add.call_args[0][0]
    assert len(entities) == len(st.active_fields())
    assert all(isinstance(e, KarlsruheSensorCitySensor) for e in entities)
