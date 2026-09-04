"""Weather provider abstraction + Open-Meteo implementation.

The risk engine never sees provider JSON directly. Providers must return
a normalized WeatherData dict.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger("weather")

OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_ELEVATION = "https://api.open-meteo.com/v1/elevation"


class WeatherProvider:
    name: str = "base"

    async def forecast(self, lat: float, lon: float) -> Dict[str, Any]:
        raise NotImplementedError

    async def history(self, lat: float, lon: float, days: int = 30) -> Dict[str, Any]:
        raise NotImplementedError


class OpenMeteoProvider(WeatherProvider):
    name = "OPEN_METEO"

    async def forecast(self, lat: float, lon: float) -> Dict[str, Any]:
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join([
                "precipitation", "rain", "temperature_2m", "relative_humidity_2m",
                "surface_pressure", "wind_speed_10m",
                "soil_moisture_0_to_1cm", "soil_moisture_1_to_3cm",
                "soil_moisture_3_to_9cm", "soil_moisture_9_to_27cm",
            ]),
            "forecast_days": 7,
            "timezone": "Asia/Kolkata",
        }
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(OPEN_METEO_FORECAST, params=params)
            r.raise_for_status()
            data = r.json()
        return self._normalize_forecast(lat, lon, data)

    async def history(self, lat: float, lon: float, days: int = 30) -> Dict[str, Any]:
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=days + 1)
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": "precipitation_sum,rain_sum,temperature_2m_mean,temperature_2m_max",
            "timezone": "Asia/Kolkata",
        }
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(OPEN_METEO_ARCHIVE, params=params)
            r.raise_for_status()
            data = r.json()
        daily = data.get("daily", {})
        return {
            "source": self.name,
            "latitude": lat, "longitude": lon,
            "days": len(daily.get("time", [])),
            "time": daily.get("time", []),
            "precipitation_sum": daily.get("precipitation_sum", []),
            "rain_sum": daily.get("rain_sum", []),
            "temperature_2m_mean": daily.get("temperature_2m_mean", []),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    def _normalize_forecast(self, lat: float, lon: float, data: Dict[str, Any]) -> Dict[str, Any]:
        h = data.get("hourly", {})
        times: List[str] = h.get("time", [])
        precip: List[float] = h.get("precipitation", []) or []
        temp: List[float] = h.get("temperature_2m", []) or []
        humid: List[float] = h.get("relative_humidity_2m", []) or []
        sm_top: List[float] = h.get("soil_moisture_0_to_1cm", []) or []
        sm_mid: List[float] = h.get("soil_moisture_3_to_9cm", []) or []
        sm_deep: List[float] = h.get("soil_moisture_9_to_27cm", []) or []
        # rolling totals we need for the model
        def _sum_last(hours: int) -> float:
            arr = precip[-hours:] if len(precip) >= hours else precip
            return round(sum(x or 0 for x in arr), 2)
        return {
            "source": self.name,
            "latitude": lat, "longitude": lon,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rainfall_1h": round(precip[-1] if precip else 0.0, 2),
            "rainfall_24h": _sum_last(24),
            "rainfall_72h": _sum_last(72),
            "rainfall_7d": _sum_last(24 * 7),
            "temperature_c": round(temp[-1] if temp else 0.0, 2),
            "humidity_pct": round(humid[-1] if humid else 0.0, 2),
            "soil_moisture_top": round((sm_top[-1] if sm_top else 0.0), 4),
            "soil_moisture_mid": round((sm_mid[-1] if sm_mid else 0.0), 4),
            "soil_moisture_deep": round((sm_deep[-1] if sm_deep else 0.0), 4),
            "forecast_hourly": {
                "time": times[:24],
                "precipitation": precip[:24],
                "temperature_2m": temp[:24],
            },
        }


class IMDProvider(WeatherProvider):
    """Placeholder — IMD credentials/endpoint documentation not available.
    Enabled only when IMD_API_KEY + IMD_BASE_URL are configured.
    """
    name = "IMD"

    def __init__(self) -> None:
        self.enabled = False

    async def forecast(self, lat: float, lon: float) -> Dict[str, Any]:
        raise RuntimeError("IMD provider not configured")

    async def history(self, lat: float, lon: float, days: int = 30) -> Dict[str, Any]:
        raise RuntimeError("IMD provider not configured")
