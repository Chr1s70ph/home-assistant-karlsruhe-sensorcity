from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

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


def _schema(options, current=None, scan_interval=DEFAULT_SCAN_INTERVAL):
    fields = {
        vol.Required(
            CONF_STATIONS,
            default=list(current) if current is not None else vol.UNDEFINED,
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[selector.SelectOptionDict(value=k, label=v) for k, v in options.items()],
                multiple=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required(CONF_SCAN_INTERVAL, default=scan_interval): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1, max=60, step=1, mode=selector.NumberSelectorMode.BOX
            )
        ),
    }
    return vol.Schema(fields)


def _user_schema(options):
    fields = {
        vol.Required(CONF_STATIONS): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[selector.SelectOptionDict(value=k, label=v) for k, v in options.items()],
                multiple=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
    }
    return vol.Schema(fields)


class KarlsruheSensorCityOptionsFlow(OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        features = await fetch_all_stations(self.hass)
        options = _station_options(features)
        current = set(self.config_entry.data.get(CONF_STATIONS, []))
        scan_interval = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        if user_input is not None:
            if not user_input.get(CONF_STATIONS):
                return self.async_show_form(
                    step_id="init",
                    data_schema=_schema(options, current, scan_interval),
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
            data_schema=_schema(options, current, scan_interval),
        )


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
