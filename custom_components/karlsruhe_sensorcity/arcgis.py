from datetime import datetime, timezone

import aiohttp

DEFAULT_PAGE_SIZE = 2000


def decode_timestamp(ms):
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


class ArcGISFeatureClient:
    def __init__(self, session: aiohttp.ClientSession, base_url: str) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")

    async def _fetch_page(self, layer, where, out_fields, order_by_fields, result_offset, result_record_count, return_geometry):
        params = {
            "where": where,
            "outFields": out_fields,
            "returnGeometry": "true" if return_geometry else "false",
            "f": "json",
        }
        if order_by_fields is not None:
            params["orderByFields"] = order_by_fields
        if result_offset:
            params["resultOffset"] = result_offset
        if result_record_count is not None:
            params["resultRecordCount"] = result_record_count
        async with self._session.get(
            f"{self._base_url}/{layer}/query", params=params
        ) as resp:
            if resp.status != 200:
                raise aiohttp.ClientResponseError(
                    resp.request_info, resp.history, status=resp.status, message="ArcGIS query failed"
                )
            data = await resp.json()
        if "error" in data:
            raise aiohttp.ClientError(str(data["error"]))
        return data

    async def query(self, layer, where="1=1", out_fields="*", order_by_fields=None, result_record_count=None, return_geometry=False):
        if result_record_count is not None:
            data = await self._fetch_page(layer, where, out_fields, order_by_fields, 0, result_record_count, return_geometry)
            return data.get("features", [])
        features = []
        offset = 0
        max_pages = 5000
        for _ in range(max_pages):
            data = await self._fetch_page(layer, where, out_fields, order_by_fields, offset, DEFAULT_PAGE_SIZE, return_geometry)
            page = data.get("features", [])
            features.extend(page)
            exceeded = data.get("exceededTransferLimit", False)
            if not exceeded or not page:
                break
            offset += len(page)
        return features
