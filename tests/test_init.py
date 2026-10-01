"""Tests for the karlsruhe_sensorcity integration package."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.karlsruhe_sensorcity import async_setup_entry, async_unload_entry
from custom_components.karlsruhe_sensorcity.const import DOMAIN


def test_domain_constant():
    assert DOMAIN == "karlsruhe_sensorcity"


def test_manifest_loads():
    import json
    from pathlib import Path

    manifest = json.loads(
        (Path(__file__).parent.parent / "custom_components/karlsruhe_sensorcity/manifest.json").read_text()
    )
    assert manifest["domain"] == "karlsruhe_sensorcity"
    assert manifest["config_flow"] is True
    assert manifest["iot_class"] == "cloud_polling"


@pytest.mark.asyncio
async def test_setup_and_unload(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"stations": ["dev1"]},
        options={"scan_interval": 5},
        entry_id="test-entry",
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.karlsruhe_sensorcity.SensorCityDataUpdateCoordinator.async_config_entry_first_refresh",
        new=AsyncMock(),
    ), patch(
        "custom_components.karlsruhe_sensorcity.SensorCityDataUpdateCoordinator.async_add_listener",
        new=MagicMock(),
    ), patch.object(
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock(return_value=True)
    ), patch.object(
        hass.config_entries, "async_unload_platforms", new=AsyncMock(return_value=True)
    ):
        assert await async_setup_entry(hass, entry) is True
        assert "test-entry" in hass.data[DOMAIN]
        assert await async_unload_entry(hass, entry) is True
        assert "test-entry" not in hass.data[DOMAIN]
