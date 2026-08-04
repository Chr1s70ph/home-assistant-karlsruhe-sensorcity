from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for station in coordinator.data.values():
        for measurement in station.active_fields():
            entities.append(KarlsruheSensorCitySensor(coordinator, station, measurement))
    async_add_entities(entities)
