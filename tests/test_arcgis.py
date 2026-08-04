"""Tests for the pure-Python ArcGIS REST client."""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.karlsruhe_sensorcity.arcgis import (
    ArcGISFeatureClient,
    decode_timestamp,
)

FIXTURES = Path(__file__).parent / "fixtures"

BASE = "https://geoportal.karlsruhe.de/ags04/rest/services/Hosted/Sensordaten_NodeRED/FeatureServer"


def load(name):
    return json.loads((FIXTURES / name).read_text())


def make_session(payload):
    """Build a fake aiohttp session whose .get returns payload JSON."""
    resp = MagicMock()
    resp.status = 200
    resp.json = AsyncMock(return_value=payload)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.get = MagicMock(return_value=resp)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


def test_decode_timestamp_none():
    assert decode_timestamp(None) is None


def test_decode_timestamp_value():
    ts = decode_timestamp(1785861504808)
    assert ts == datetime(2026, 8, 4, 16, 38, 24, 808000, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_query_single_page_no_exceed():
    payload = load("temp_station.json")
    payload["exceededTransferLimit"] = False
    session = make_session(payload)
    client = ArcGISFeatureClient(session, BASE)
    feats = await client.query(1)
    assert len(feats) == 1
    assert feats[0]["attributes"]["device_id"] == "fa0d211f-3f9c-423c-a5ae-fd34424ab649"
    assert feats[0]["geometry"] == {"x": 8.468165484000053, "y": 48.97157811000005}


@pytest.mark.asyncio
async def test_query_respects_result_record_count():
    payload = load("temp_station.json")
    session = make_session(payload)
    client = ArcGISFeatureClient(session, BASE)
    await client.query(1, result_record_count=1)
    args, kwargs = session.get.call_args
    url = str(args[0])
    assert "resultRecordCount=1" in url or kwargs.get("params", {}).get("resultRecordCount") == 1


@pytest.mark.asyncio
async def test_query_paginates_when_exceeded(tmp_path):
    page1 = {"features": [{"attributes": {"objectid": 1}}, {"attributes": {"objectid": 2}}], "exceededTransferLimit": True}
    page2 = {"features": [{"attributes": {"objectid": 3}}], "exceededTransferLimit": False}

    resp1 = MagicMock(); resp1.status = 200; resp1.json = AsyncMock(return_value=page1)
    resp1.__aenter__ = AsyncMock(return_value=resp1); resp1.__aexit__ = AsyncMock(return_value=None)
    resp2 = MagicMock(); resp2.status = 200; resp2.json = AsyncMock(return_value=page2)
    resp2.__aenter__ = AsyncMock(return_value=resp2); resp2.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock(); session.get = MagicMock(side_effect=[resp1, resp2])

    client = ArcGISFeatureClient(session, BASE)
    feats = await client.query(1)
    assert len(feats) == 3
    assert [f["attributes"]["objectid"] for f in feats] == [1, 2, 3]
    assert session.get.call_count == 2


@pytest.mark.asyncio
async def test_query_http_error_raises():
    resp = MagicMock(); resp.status = 500
    resp.__aenter__ = AsyncMock(return_value=resp); resp.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock(); session.get = MagicMock(return_value=resp)
    client = ArcGISFeatureClient(session, BASE)
    with pytest.raises(aiohttp.ClientResponseError):
        await client.query(1)
