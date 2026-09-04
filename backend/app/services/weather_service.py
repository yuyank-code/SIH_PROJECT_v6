"""Weather service — provider-agnostic entry point used by risk engine + API."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

import httpx

from app.providers.weather.open_meteo import (
    OpenMeteoProvider,
    OPEN_METEO_ELEVATION,
)

log = logging.getLogger("weather_service")

_provider = OpenMeteoProvider()
_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_S = 300


def _cache_key(lat: float, lon: float, kind: str) -> str:
    return f"{kind}:{round(lat,3)}:{round(lon,3)}"


async def get_current(lat: float, lon: float) -> Dict[str, Any]:
    key = _cache_key(lat, lon, "cur")
    now = datetime.now(timezone.utc).timestamp()
    hit = _cache.get(key)
    if hit and now - hit["_ts"] < CACHE_TTL_S:
        return hit["data"]
    try:
        data = await _provider.forecast(lat, lon)
        _cache[key] = {"_ts": now, "data": data}
        return data
    except Exception as exc:  # noqa: BLE001
        log.warning("weather forecast failed: %s", exc)
        if hit:
            data = dict(hit["data"])
            data["stale"] = True
            return data
        return {"source": _provider.name, "unavailable": True, "reason": str(exc)}


async def get_history(lat: float, lon: float, days: int = 30) -> Dict[str, Any]:
    try:
        return await _provider.history(lat, lon, days)
    except Exception as exc:  # noqa: BLE001
        log.warning("weather history failed: %s", exc)
        return {"source": _provider.name, "unavailable": True, "reason": str(exc)}


async def get_elevation(lat: float, lon: float) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(OPEN_METEO_ELEVATION, params={"latitude": lat, "longitude": lon})
            r.raise_for_status()
            j = r.json()
        elev = (j.get("elevation") or [None])[0]
        return {"source": "OPEN_METEO", "latitude": lat, "longitude": lon, "elevation_m": elev}
    except Exception as exc:  # noqa: BLE001
        return {"source": "OPEN_METEO", "unavailable": True, "reason": str(exc)}
