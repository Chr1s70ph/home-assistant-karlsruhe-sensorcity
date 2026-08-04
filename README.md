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

1. **Settings -> Devices & Services -> Add Integration** -> "Karlsruhe
   SensorCity".
2. Select the stations you want from the list. (Searchable; multi-select.)
3. Done - entities appear under a device per station.

### Options

- **Settings -> Devices & Services -> Karlsruhe SensorCity -> Configure** to add
  or remove stations and set the polling interval (1-60 minutes, default 5).

## Data source

Public, read-only ArcGIS REST FeatureServer behind the official
[SensorCity dashboard](https://geoportal.karlsruhe.de/sensorcity/Dashboard/).
No API key required. The integration polls the live layer every 5 minutes by
default and, for weather stations, enriches with the newest archive row for
extra measurements (precipitation; PM/UV/wind when the source publishes them).

> Archive history (rolling windows) is not imported in v1 - only live values.

## Limitations

- Archive layers are rolling windows; only the newest row per weather station
  is used (live values, not history).
- Some fields (PM10/PM2.5/UV/wind) exist in the source schema but are
  currently unpopulated; entities are created only for fields a station
  actually reports, so you won't see dead entities.

## License

MIT
