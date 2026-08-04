"""Tests for Station model and measurement catalog."""
import json
from pathlib import Path

from custom_components.karlsruhe_sensorcity.models import (
    CATALOG,
    SENTINELS,
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


def test_parse_water_station_coordinates():
    feat = load("water_station.json")["features"][0]
    st = parse_station(feat)
    assert st.lat == 49.03897740000008
    assert st.lon == 8.305563800000073


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
    assert "soil_moisture_at_depth_01" in fields
    assert "soil_temperature_at_depth_51" in fields
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
