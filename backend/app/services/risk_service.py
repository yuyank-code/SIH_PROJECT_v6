"""Risk engine: builds V5 model features from live weather + stored terrain,
runs inference, and returns explainable risk output.

The V5 model wants 13 features. Weather data provides 8 rainfall features
(1d, 3d, 7d, 15d, 30d, max_rainfall_3d, max_rainfall_7d, rainy_days_7d).
Terrain data (elevation_m, slope_deg, aspect_sin, aspect_cos, curvature_1_m)
must come from stored zone metadata — it is NEVER fabricated at request time.
If a zone has no stored terrain, we return `feature_unavailable`.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.services.ml_service import ml_service
from app.services import weather_service

log = logging.getLogger("risk_service")


def _rainfall_features_from_history(history: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """Compute rolling rainfall features from Open-Meteo daily archive.

    history["precipitation_sum"] is a chronological list ending yesterday
    (Open-Meteo archive lags 1-2 days). We approximate 1d as last day,
    3d = sum last 3, etc. rainy_days_7d = number of days in last 7 with rain > 1mm.
    """
    if history.get("unavailable"):
        return None
    p = history.get("precipitation_sum") or []
    if len(p) < 30:
        return None
    p = [float(x or 0) for x in p]

    def tail_sum(n: int) -> float:
        return round(sum(p[-n:]), 2)

    def tail_max_window(window: int, n_days: int) -> float:
        best = 0.0
        for i in range(max(0, len(p) - n_days), len(p) - window + 1):
            best = max(best, sum(p[i:i + window]))
        return round(best, 2)

    rainy_7 = sum(1 for x in p[-7:] if x > 1.0)
    return {
        "rainfall_1d": tail_sum(1),
        "rainfall_3d": tail_sum(3),
        "rainfall_7d": tail_sum(7),
        "rainfall_15d": tail_sum(15),
        "rainfall_30d": tail_sum(30),
        "max_rainfall_3d": tail_max_window(3, 30),
        "max_rainfall_7d": tail_max_window(7, 30),
        "rainy_days_7d": float(rainy_7),
    }


def _terrain_features_from_zone(zone: Dict[str, Any]) -> Optional[Dict[str, float]]:
    t = zone.get("terrain") or {}
    required = ["elevation_m", "slope_deg", "aspect_sin", "aspect_cos", "curvature_1_m"]
    if not all(k in t for k in required):
        return None
    return {k: float(t[k]) for k in required}


async def predict_zone(zone: Dict[str, Any], rainfall_override: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    lat = zone["centroid"]["lat"]
    lon = zone["centroid"]["lon"]
    terrain = _terrain_features_from_zone(zone)
    if terrain is None:
        return {"error": "feature_unavailable", "detail": "zone missing terrain features", "zone_id": zone.get("zone_id")}

    if rainfall_override is not None:
        rainfall = rainfall_override
    else:
        hist = await weather_service.get_history(lat, lon, days=32)
        rainfall = _rainfall_features_from_history(hist)
        if rainfall is None:
            return {
                "error": "feature_unavailable",
                "detail": "Open-Meteo historical rainfall unavailable",
                "zone_id": zone.get("zone_id"),
            }

    features = {**rainfall, **terrain}
    result = ml_service.predict_one(features)
    result["zone_id"] = zone.get("zone_id")
    result["district"] = zone.get("district")
    result["state"] = zone.get("state")
    result["source_map"] = {
        "rainfall": "OPEN_METEO" if rainfall_override is None else "SIMULATED",
        "terrain": "DEM" if zone.get("terrain_source") == "DEM" else "DEMO",
    }
    result["features_used"] = features
    return result


def classify_response_priority(prediction: Dict[str, Any], zone: Dict[str, Any]) -> Dict[str, Any]:
    """P1-P4 emergency response classification.

    Considers only factors we actually have. If population/roads/villages data
    are missing, we mark them as `unknown` and reduce confidence.
    """
    sev = prediction.get("severity", "LOW")
    known: List[str] = []
    unknown: List[str] = []
    score = 0
    if sev == "CRITICAL":
        score += 40; known.append("severity=CRITICAL")
    elif sev == "HIGH":
        score += 25; known.append("severity=HIGH")
    elif sev == "MEDIUM":
        score += 10; known.append("severity=MEDIUM")
    else:
        known.append("severity=LOW")

    pop = zone.get("population")
    if pop is None:
        unknown.append("population")
    else:
        if pop > 5000: score += 15
        elif pop > 1000: score += 8
        known.append(f"population={pop}")

    nearby_road_blocked = zone.get("road_blocked", False)
    if nearby_road_blocked:
        score += 20; known.append("road=BLOCKED")
    village_isolation = zone.get("isolated_villages", 0)
    if village_isolation and village_isolation > 0:
        score += 10; known.append(f"isolated_villages={village_isolation}")
    recent_report = zone.get("recent_field_report", False)
    if recent_report:
        score += 10; known.append("recent_field_report=True")

    if score >= 55:
        priority = "P1"; label = "IMMEDIATE"
    elif score >= 30:
        priority = "P2"; label = "URGENT"
    elif score >= 15:
        priority = "P3"; label = "MONITOR"
    else:
        priority = "P4"; label = "LOW"
    return {
        "priority": priority,
        "label": label,
        "score": score,
        "known_factors": known,
        "unknown_factors": unknown,
    }
