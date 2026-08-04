"""Tests for the karlsruhe_sensorcity integration package."""
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
    assert manifest["version"] == "0.1.0"
