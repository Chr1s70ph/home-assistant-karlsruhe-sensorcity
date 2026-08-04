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
        return (
            self.coordinator.last_update_success
            and self.station.device_id in self.coordinator.data
        )

    def _current_station(self) -> Station | None:
        return self.coordinator.data.get(self.station.device_id)
