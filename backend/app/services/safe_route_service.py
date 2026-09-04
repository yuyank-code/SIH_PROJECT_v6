"""Safe route & shelter recommendation (Feature K).

The risk model answers *"is this slope dangerous?"*. It leaves the question a
person actually asks unanswered: **"then where do I go?"** This module answers
that one, from data the platform already holds — shelters, road status, zone
predictions and terrain.

What this module deliberately does **not** do
---------------------------------------------
It is **not a routing engine**. There is no OSRM / Valhalla / Google Directions
call here, no road-graph traversal, and no turn-by-turn navigation. We hold road
*centrelines and status*, not a routable network with turn restrictions, so any
"route" we drew would be a guess dressed up as instructions. In a landslide
evacuation that is the most dangerous fabrication this platform could produce.

So instead of pretending, this module reports what it can actually justify:

* a **great-circle distance and bearing** to each shelter (computed here, exact);
* a **walking estimate at a stated pace**, labelled as an estimate, never an ETA;
* **known hazards** on the way — roads the platform records as BLOCKED or
  RESTRICTED near the corridor;
* a **suitability score with its reasons listed**, so an operator or a citizen
  can see precisely why one shelter outranked another;
* **movement guidance** that is correct for landslides specifically — the first
  move is lateral, out of the run-out path, *not* along the bearing.

Everything derived carries a `source` tag. Anything unknown stays `None` and is
said to be unknown; it is never defaulted to a convenient number.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional

# --- tunables, published in the payload so the numbers on screen are auditable
WALK_PACE_KMH = 4.0          # ordinary adult walking pace on a road
RISK_ZONE_RADIUS_KM = 5.0    # how close a predicted zone must be to count against a shelter
HAZARD_RADIUS_KM = 3.0       # how close a blocked road must be to be worth warning about
LATERAL_FIRST_M = 100        # move this far across the slope before heading anywhere
WALKABLE_RADIUS_KM = 15.0    # beyond this, "go there" means transport, not walking

EARTH_RADIUS_KM = 6371.0088  # IUGG mean earth radius

SOURCE_GEOMETRY = "DERIVED_FROM_COORDINATES"
SOURCE_ROAD_STATUS = "DERIVED_FROM_ROAD_STATUS"
SOURCE_PREDICTION = "DERIVED_FROM_PREDICTION"
SOURCE_SHELTER_RECORD = "SHELTER_RECORD"
SOURCE_UNAVAILABLE = "UNAVAILABLE"

HAZARD_ROAD_STATES = {"BLOCKED", "RESTRICTED"}
_SEVERITY_PENALTY = {"CRITICAL": 45, "HIGH": 30, "MEDIUM": 12, "LOW": 0}
_COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


# ---------------------------------------------------------------------------
# Geometry — plain, checkable maths
# ---------------------------------------------------------------------------
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial great-circle bearing from point 1 to point 2, in degrees from north."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def compass_point(deg: Optional[float]) -> Optional[str]:
    """16-point compass label for a bearing ('NNE', 'SW', ...)."""
    if deg is None:
        return None
    return _COMPASS[int((deg % 360.0) / 22.5 + 0.5) % 16]


def walk_estimate_minutes(distance_km: Optional[float], pace_kmh: float = WALK_PACE_KMH) -> Optional[int]:
    """Rough walking time at a stated pace, or None if walking is not a real option.

    Past `WALKABLE_RADIUS_KM` this deliberately returns None instead of a number.
    Rendering "4001 min" next to a shelter 267 km away technically answers the
    arithmetic while implying the journey is something a person could set off and
    do on foot. Silence is more honest, and the caller shows a transport note.
    """
    if distance_km is None or pace_kmh <= 0:
        return None
    if distance_km > WALKABLE_RADIUS_KM:
        return None
    return int(round(distance_km / pace_kmh * 60.0))


# ---------------------------------------------------------------------------
# Hazards along the way — from recorded road status, nothing inferred
# ---------------------------------------------------------------------------
def road_hazards(roads: Iterable[Dict[str, Any]], radius_km: float = HAZARD_RADIUS_KM) -> List[Dict[str, Any]]:
    """Roads near the caller that the platform records as blocked or restricted.

    This is a *known-hazard list*, not a claim of completeness: a road nobody has
    reported on reads UNKNOWN and is simply absent here. The UI must say so.
    """
    out: List[Dict[str, Any]] = []
    for r in roads or []:
        status = (r.get("status") or "UNKNOWN").upper()
        if status not in HAZARD_ROAD_STATES:
            continue
        dist = r.get("distance_km")
        if dist is not None and dist > radius_km:
            continue
        out.append({
            "road_id": r.get("road_id"),
            "name": r.get("name") or r.get("road_id"),
            "status": status,
            "distance_km": round(dist, 2) if dist is not None else None,
            "advice": ("Do not use this road — it is recorded as blocked."
                       if status == "BLOCKED"
                       else "Use this road only if you have no alternative — it is recorded as restricted."),
            "source": SOURCE_ROAD_STATUS,
        })
    out.sort(key=lambda h: (h["status"] != "BLOCKED", h["distance_km"] if h["distance_km"] is not None else 9e9))
    return out


def nearest_risk_zone(lat: float, lon: float, zones: Iterable[Dict[str, Any]],
                      radius_km: float = RISK_ZONE_RADIUS_KM) -> Optional[Dict[str, Any]]:
    """The closest predicted zone within `radius_km`, or None if nothing is near.

    `zones` are rows carrying a centroid and (optionally) a latest prediction.
    A zone with no prediction contributes no severity — it is not treated as safe,
    it is treated as unknown.
    """
    best: Optional[Dict[str, Any]] = None
    for z in zones or []:
        centroid = z.get("centroid") or {}
        zlat, zlon = centroid.get("lat"), centroid.get("lon")
        if zlat is None or zlon is None:
            continue
        d = haversine_km(lat, lon, zlat, zlon)
        if d > radius_km:
            continue
        if best is None or d < best["distance_km"]:
            latest = z.get("latest") or {}
            best = {
                "zone_id": z.get("zone_id"),
                "name": z.get("name"),
                "distance_km": d,
                "severity": latest.get("severity"),
                "probability": latest.get("probability"),
                "source": SOURCE_PREDICTION if latest.get("severity") else SOURCE_UNAVAILABLE,
            }
    if best:
        best["distance_km"] = round(best["distance_km"], 2)
    return best


# ---------------------------------------------------------------------------
# Shelter assessment & ranking
# ---------------------------------------------------------------------------
def _capacity_view(shelter: Dict[str, Any]) -> Dict[str, Any]:
    """Spare capacity, or an explicit statement that it was never recorded.

    A missing occupancy count must not read as "empty" — that is exactly the kind
    of blank-means-zero error that sends a family to a full camp at night.
    """
    cap, occ = shelter.get("capacity"), shelter.get("current_occupancy")
    if cap is None:
        return {"capacity": None, "occupancy": occ, "headroom": None,
                "known": False, "note": "Capacity not recorded", "source": SOURCE_UNAVAILABLE}
    if occ is None:
        return {"capacity": cap, "occupancy": None, "headroom": None,
                "known": False, "note": "Occupancy not counted yet", "source": SOURCE_UNAVAILABLE}
    return {"capacity": cap, "occupancy": occ, "headroom": cap - occ,
            "known": True, "note": None, "source": SOURCE_SHELTER_RECORD}


def assess_shelter(origin_lat: float, origin_lon: float, shelter: Dict[str, Any],
                   zones: Optional[Iterable[Dict[str, Any]]] = None,
                   origin_elevation_m: Optional[float] = None) -> Dict[str, Any]:
    """Score one shelter for one person standing at one point.

    Returns the shelter enriched with distance, bearing, walking estimate, spare
    capacity, the risk of the ground it stands on, a 0-100 suitability score and
    — crucially — `reasons`, the itemised list of what moved that score. A score
    nobody can interrogate is not worth showing.
    """
    zones = list(zones or [])
    slat, slon = shelter.get("lat"), shelter.get("lon")
    status = (shelter.get("status") or "OPEN").upper()

    distance_km = shelter.get("distance_km")
    if distance_km is None and slat is not None and slon is not None:
        distance_km = haversine_km(origin_lat, origin_lon, slat, slon)
    bearing = (bearing_deg(origin_lat, origin_lon, slat, slon)
               if slat is not None and slon is not None else None)

    capacity = _capacity_view(shelter)
    dest_risk = nearest_risk_zone(slat, slon, zones) if slat is not None and slon is not None else None

    score = 100.0
    reasons: List[str] = []
    warnings: List[str] = []

    # --- distance: 4 points per km over the first 10 km, then a second, gentler
    #     slope that never saturates. An earlier version capped the penalty at 40,
    #     which made every shelter beyond 10 km score identically on distance — so
    #     a shelter 267 km away tied with one 10 km away and then won on having no
    #     risk zone beside it. The engine cheerfully recommended a 66-hour walk.
    #     Distance must keep discriminating, all the way out.
    requires_transport = distance_km is not None and distance_km > WALKABLE_RADIUS_KM
    if distance_km is not None:
        penalty = min(40.0, distance_km * 4.0)
        if distance_km > WALKABLE_RADIUS_KM:
            penalty += min(45.0, (distance_km - WALKABLE_RADIUS_KM) * 1.5)
        score -= penalty
        reasons.append(f"{distance_km:.1f} km away (-{penalty:.0f})")
        if requires_transport:
            warnings.append(
                f"This is {distance_km:.0f} km away — too far to walk. You need a vehicle "
                f"or organised transport to reach it."
            )
    else:
        reasons.append("distance unknown — shelter has no recorded location")

    # --- operational status
    if status == "CLOSED":
        score -= 100.0
        warnings.append("This shelter is recorded as CLOSED.")
        reasons.append("closed (-100)")
    elif status == "FULL":
        score -= 35.0
        warnings.append("This shelter is recorded as FULL — call ahead before travelling.")
        reasons.append("marked full (-35)")
    elif status == "STANDBY":
        score -= 15.0
        warnings.append("This shelter is on standby and may not be staffed yet.")
        reasons.append("on standby (-15)")

    # --- spare capacity, only when it is actually known
    if capacity["known"]:
        headroom = capacity["headroom"]
        if headroom is not None and headroom <= 0:
            score -= 30.0
            warnings.append("No spare capacity is recorded here.")
            reasons.append("no spare capacity (-30)")
        elif headroom is not None and capacity["capacity"] and headroom < capacity["capacity"] * 0.1:
            score -= 10.0
            reasons.append(f"nearly full, {headroom} place(s) left (-10)")
        else:
            reasons.append(f"{headroom} place(s) free")
    else:
        reasons.append(capacity["note"].lower())

    # --- is the shelter itself under a dangerous slope?
    if dest_risk and dest_risk.get("severity") in _SEVERITY_PENALTY:
        sev = dest_risk["severity"]
        penalty = _SEVERITY_PENALTY[sev]
        if penalty:
            score -= penalty
            warnings.append(
                f"This shelter sits {dest_risk['distance_km']} km from {dest_risk['name']}, "
                f"currently rated {sev}."
            )
            reasons.append(f"near a {sev} zone (-{penalty})")

    # --- higher ground is better, but only when both elevations are known
    shelter_elev = shelter.get("elevation_m")
    if shelter_elev is not None and origin_elevation_m is not None:
        climb = shelter_elev - origin_elevation_m
        if climb <= -50:
            score -= 10.0
            reasons.append(f"{abs(int(climb))} m lower than you (-10)")
        elif climb >= 50:
            score += 5.0
            reasons.append(f"{int(climb)} m higher than you (+5)")
    else:
        reasons.append("elevation gain unknown")

    out = dict(shelter)
    out.update({
        "distance_km": round(distance_km, 2) if distance_km is not None else None,
        "bearing_deg": round(bearing, 1) if bearing is not None else None,
        "direction": compass_point(bearing),
        "walk_minutes_estimate": walk_estimate_minutes(distance_km),
        "walk_estimate_basis": (
            f"straight-line distance at {WALK_PACE_KMH:g} km/h — a floor, not a routed travel time"
            if not requires_transport else
            f"beyond {WALKABLE_RADIUS_KM:g} km — walking is not a realistic option, transport required"
        ),
        "requires_transport": requires_transport,
        "capacity_view": capacity,
        "destination_risk": dest_risk,
        "status": status,
        "reachable": status != "CLOSED",
        "suitability": int(max(0.0, min(100.0, round(score)))),
        "reasons": reasons,
        "warnings": warnings,
        "source": shelter.get("source") or SOURCE_SHELTER_RECORD,
        "geometry_source": SOURCE_GEOMETRY,
    })
    return out


def rank_shelters(origin_lat: float, origin_lon: float, shelters: Iterable[Dict[str, Any]],
                  zones: Optional[Iterable[Dict[str, Any]]] = None,
                  origin_elevation_m: Optional[float] = None,
                  limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Assess every shelter and sort best-first.

    Closed shelters are kept in the list rather than hidden — a person who knows
    the nearest hall is shut will not walk to it — but they sort to the bottom.

    Walkability is a *sort key*, not just a score input. Scores are a weighted sum
    and a weighted sum can always be gamed by an unlucky combination of factors;
    making "can this person actually walk there?" its own ordering term guarantees
    a reachable nearby shelter outranks a distant one no matter how the individual
    penalties happen to land.
    """
    assessed = [assess_shelter(origin_lat, origin_lon, s, zones, origin_elevation_m) for s in (shelters or [])]
    assessed.sort(key=lambda s: (
        not s["reachable"],
        s["requires_transport"],
        -s["suitability"],
        s["distance_km"] if s["distance_km"] is not None else 9e9,
    ))
    for i, s in enumerate(assessed, start=1):
        s["rank"] = i
    return assessed[:limit] if limit else assessed


# ---------------------------------------------------------------------------
# What to actually do — landslide-specific, and ordered
# ---------------------------------------------------------------------------
def movement_guidance(origin_severity: Optional[str], hazards: List[Dict[str, Any]],
                      has_shelter: bool, transport_only: bool = False) -> List[Dict[str, Any]]:
    """Immediate actions, most urgent first.

    Landslide movement advice is not "head towards the shelter". The first move
    is **across** the slope, out of the run-out path — a debris flow travels down
    the fall line far faster than a person can walk along it. Only once you are
    off that line does the shelter bearing become the thing to follow.

    `transport_only` means every known shelter is beyond walking range. The honest
    instruction then is *not* "start walking" — it is to get to safe ground nearby
    and call for a vehicle. Telling someone to walk 60 km through active terrain
    would be worse than telling them nothing.
    """
    if transport_only:
        onward = ("No shelter is within walking distance of you. Do not set out on foot. Get to open, "
                  "level ground clear of slopes, then call the helpline or emergency services and ask "
                  "for transport — the shelters listed are reachable only by vehicle.")
    elif has_shelter:
        onward = ("Once you are clear of the slide path, head for the shelter below — the direction "
                  "given is a straight-line bearing, so follow real roads and tracks to get there.")
    else:
        onward = ("Once you are clear of the slide path, move to open, level, firm ground away from "
                  "cut slopes and retaining walls, and wait for instructions.")

    steps: List[Dict[str, Any]] = [
        {"code": "MOVE_LATERAL", "priority": 1,
         "text": (f"Move sideways across the slope, not downhill and not uphill along it. "
                  f"Put at least {LATERAL_FIRST_M} m between you and the line the debris would "
                  f"travel down before you go anywhere else.")},
        {"code": "AVOID_CHANNELS", "priority": 2,
         "text": "Stay out of stream beds, gullies and narrow valley floors. Debris and water funnel into them."},
        {"code": "THEN_HEAD", "priority": 3, "text": onward},
        {"code": "TELL_SOMEONE", "priority": 4,
         "text": "Tell someone where you are going. If you have signal, submit a report so responders can see the ground truth."},
        {"code": "DO_NOT_RETURN", "priority": 5,
         "text": "Do not go back for belongings. Slopes commonly fail a second time within hours of the first movement."},
    ]
    if (origin_severity or "").upper() in {"HIGH", "CRITICAL"}:
        steps.insert(0, {
            "code": "EVACUATE_NOW", "priority": 0,
            "text": f"Your location is inside a zone currently rated {origin_severity}. Leave now — do not wait for a siren.",
        })
    if any(h["status"] == "BLOCKED" for h in hazards):
        steps.append({
            "code": "ROAD_BLOCKED", "priority": 6,
            "text": "A road near you is recorded as blocked. Check the hazard list before choosing your way out.",
        })
    return steps


def _elevation_of(zone: Optional[Dict[str, Any]]) -> Optional[float]:
    """Zone elevation, wherever the caller's zone shape happens to keep it.

    `repo.list_zones()` nests terrain under `terrain`, while the raw table row has
    it top-level. Accept both rather than silently returning None for one of them.
    """
    if not zone:
        return None
    if zone.get("elevation_m") is not None:
        return zone["elevation_m"]
    return (zone.get("terrain") or {}).get("elevation_m")


def build_recommendation(origin_lat: float, origin_lon: float,
                         shelters: Iterable[Dict[str, Any]],
                         roads: Optional[Iterable[Dict[str, Any]]] = None,
                         zones: Optional[Iterable[Dict[str, Any]]] = None,
                         limit: int = 5) -> Dict[str, Any]:
    """The whole answer to "where do I go?", assembled and self-describing."""
    zones = list(zones or [])
    origin_zone = nearest_risk_zone(origin_lat, origin_lon, zones)
    origin_elevation = None
    if origin_zone:
        match = next((z for z in zones if z.get("zone_id") == origin_zone.get("zone_id")), None)
        origin_elevation = _elevation_of(match)

    hazards = road_hazards(roads or [])
    ranked = rank_shelters(origin_lat, origin_lon, shelters, zones, origin_elevation, limit=limit)
    reachable = [s for s in ranked if s["reachable"]]
    walkable = [s for s in reachable if not s["requires_transport"]]
    # Recommend something a person can actually act on. If nothing is walkable we
    # still name the best option — withholding it helps nobody — but the payload
    # flags that reaching it needs a vehicle, and the guidance says so first.
    recommended = walkable[0] if walkable else (reachable[0] if reachable else None)
    transport_only = bool(reachable) and not walkable

    return {
        "origin": {"lat": origin_lat, "lon": origin_lon,
                   "elevation_m": origin_elevation,
                   "elevation_source": "NEAREST_ZONE_TERRAIN" if origin_elevation is not None else SOURCE_UNAVAILABLE},
        "origin_risk": origin_zone,
        "shelters": ranked,
        "recommended": recommended,
        "transport_only": transport_only,
        "hazards": hazards,
        "guidance": movement_guidance(origin_zone.get("severity") if origin_zone else None,
                                      hazards, bool(reachable), transport_only),
        "assumptions": {
            "walking_pace_kmh": WALK_PACE_KMH,
            "walkable_radius_km": WALKABLE_RADIUS_KM,
            "risk_zone_radius_km": RISK_ZONE_RADIUS_KM,
            "hazard_radius_km": HAZARD_RADIUS_KM,
            "routing": ("No routing engine is used. Distances and bearings are straight-line "
                        "great-circle values; road hazards come from recorded road status only, "
                        "so a road with no status recorded is absent from the hazard list rather "
                        "than known to be safe."),
        },
        "counts": {"shelters_considered": len(ranked), "shelters_reachable": len(reachable),
                   "shelters_walkable": len(walkable), "hazards_known": len(hazards)},
    }
