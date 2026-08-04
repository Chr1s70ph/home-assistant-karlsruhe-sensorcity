import logging
from datetime import timedelta

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
            except Exception as exc:  # noqa: BLE001
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
