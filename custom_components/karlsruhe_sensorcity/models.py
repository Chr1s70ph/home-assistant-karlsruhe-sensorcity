from dataclasses import dataclass
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
