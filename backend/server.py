"""NER-SLIDE Backend — Supabase/PostGIS API."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BACKEND_DIR, ".env"))

from app.services.ml_service import ml_service
from app.services import weather_service, risk_service, terrain_service, monitoring_service
from app.services import safe_route_service, citizen_service
from app.services.llm_service import explain_risk, build_alert_translations, SUPPORTED_LANGUAGES
from app.data import recovery_playbook as playbook
from app.db import supabase_repo as repo
from app.auth_middleware import install_auth_middleware
from app.authorization import require_roles

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("nerslide")

app = FastAPI(title="NER-SLIDE API", version="2.1.0-supabase")
api = APIRouter(prefix="/api")
install_auth_middleware(app)

@app.on_event("startup")
async def startup() -> None:
    await repo.client()
    log.info("Supabase persistence initialized")

@app.on_event("shutdown")
async def shutdown() -> None:
    await repo.close()

@api.get("/health")
async def health() -> Dict[str, Any]:
    return {"status": "ok", "model_loaded": ml_service.model is not None, "model_version": ml_service.version,
            "feature_count": len(ml_service.feature_list()), "persistence": "SUPABASE", "timestamp": datetime.now(timezone.utc).isoformat()}

@api.get("/model/info")
async def model_info() -> Dict[str, Any]:
    return {"version": ml_service.version, "features": ml_service.feature_list(), "threshold_operational": 0.15,
            "severity_bands": [{"label": x[0], "lo": x[1], "hi": x[2]} for x in [("LOW",0.0,0.15),("MEDIUM",0.15,0.35),("HIGH",0.35,0.65),("CRITICAL",0.65,1.01)]]}

@api.get("/me")
async def me(request: Request) -> Dict[str, Any]:
    return {"user": request.state.supabase_user, "profile": request.state.profile}

class PredictRequest(BaseModel):
    features: Dict[str, float]

@api.post("/predictions/predict")
async def predict(req: PredictRequest) -> Dict[str, Any]:
    try:
        return ml_service.predict_one(req.features)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

class ZonePredictRequest(BaseModel):
    zone_id: str
    rainfall_override: Optional[Dict[str, float]] = None

@api.post("/predictions/zone")
async def predict_zone_api(req: ZonePredictRequest, _=Depends(require_roles("AUTHORITY"))) -> Dict[str, Any]:
    zone = await repo.get_zone(req.zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="zone_not_found")
    result = await risk_service.predict_zone(zone, req.rainfall_override)
    if "error" in result:
        raise HTTPException(status_code=424, detail=result)
    priority = risk_service.classify_response_priority(result, zone)
    return await repo.upsert_prediction(req.zone_id, result, priority)

@api.get("/predictions/{zone_id}")
async def get_latest_prediction(zone_id: str) -> Dict[str, Any]:
    result = await repo.get_latest_prediction(zone_id)
    if not result:
        raise HTTPException(status_code=404, detail="no_prediction_yet")
    return result

@api.post("/predictions/run-all")
async def run_all(_=Depends(require_roles("AUTHORITY"))) -> Dict[str, Any]:
    zones = await repo.list_zones()
    ok = failed = 0
    for zone in zones:
        try:
            result = await risk_service.predict_zone(zone)
            if "error" in result:
                failed += 1
                continue
            priority = risk_service.classify_response_priority(result, zone)
            await repo.upsert_prediction(zone["zone_id"], result, priority)
            ok += 1
        except Exception as exc:
            log.warning("run-all zone=%s failed=%s", zone.get("zone_id"), exc)
            failed += 1
    return {"ok": ok, "failed": failed}

async def _zones_payload(state: Optional[str] = None, severity: Optional[str] = None) -> List[Dict[str, Any]]:
    zones = await repo.list_zones(state)
    predictions = {p.get("zone_id"): p for p in await repo.get_predictions()}
    out = []
    for zone in zones:
        p = predictions.get(zone["zone_id"])
        if p:
            zone["latest"] = {"severity": p.get("severity"), "risk_score": p.get("risk_score"), "probability": p.get("probability"), "updated_at": p.get("predicted_at")}
        if severity and (not p or p.get("severity") != severity):
            continue
        out.append(zone)
    return out

@api.get("/zones")
async def list_zones(state: Optional[str] = None, severity: Optional[str] = None) -> List[Dict[str, Any]]:
    return await _zones_payload(state, severity)

@api.get("/public/zones")
async def public_zones(state: Optional[str] = None, severity: Optional[str] = None) -> List[Dict[str, Any]]:
    return await _zones_payload(state, severity)

@api.get("/zones/{zone_id}")
async def get_zone(zone_id: str) -> Dict[str, Any]:
    zone = await repo.get_zone(zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="zone_not_found")
    p = await repo.get_latest_prediction(zone_id)
    if p: zone["latest"] = p
    zone["sensors"] = [s for s in await repo.list_sensors() if s.get("zone_id") == zone.get("id")]
    zone["roads_nearby"] = await repo.nearest_roads(zone["centroid"]["lat"], zone["centroid"]["lon"], 3)
    zone["villages_nearby"] = await repo.nearest_villages(zone["centroid"]["lat"], zone["centroid"]["lon"], 3)
    return zone

async def _gis_risk_zones() -> Dict[str, Any]:
    zones = await repo.list_zones()
    predictions = {p.get("zone_id"): p for p in await repo.get_predictions()}
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": z.get("geometry"), "properties": {"zone_id": z["zone_id"], "name": z["name"], "state": z["state"], "district": z["district"], "severity": (predictions.get(z["zone_id"]) or {}).get("severity", "UNKNOWN"), "risk_score": (predictions.get(z["zone_id"]) or {}).get("risk_score"), "probability": (predictions.get(z["zone_id"]) or {}).get("probability"), "population": z.get("population")}} for z in zones]}

@api.get("/gis/risk-zones")
async def gis_risk_zones() -> Dict[str, Any]: return await _gis_risk_zones()

@api.get("/public/gis/risk-zones")
async def public_gis_risk_zones() -> Dict[str, Any]: return await _gis_risk_zones()

async def _gis_heatmap() -> List[Dict[str, Any]]:
    zones = await repo.list_zones()
    predictions = {p.get("zone_id"): p for p in await repo.get_predictions()}
    return [{"lat": z["centroid"]["lat"], "lon": z["centroid"]["lon"], "intensity": float((predictions.get(z["zone_id"]) or {}).get("probability", 0.0)), "zone_id": z["zone_id"], "severity": (predictions.get(z["zone_id"]) or {}).get("severity", "UNKNOWN")} for z in zones]

@api.get("/gis/heatmap")
async def gis_heatmap() -> List[Dict[str, Any]]: return await _gis_heatmap()

@api.get("/public/gis/heatmap")
async def public_gis_heatmap() -> List[Dict[str, Any]]: return await _gis_heatmap()

async def _gis_sensors() -> Dict[str, Any]:
    sensors = await repo.list_sensors()
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]}, "properties": s} for s in sensors]}

@api.get("/gis/sensors")
async def gis_sensors() -> Dict[str, Any]: return await _gis_sensors()

async def _gis_roads() -> Dict[str, Any]:
    roads = await repo.list_roads()
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": r["geometry"], "properties": {k: v for k, v in r.items() if k != "geometry"}} for r in roads]}

@api.get("/gis/roads")
async def gis_roads() -> Dict[str, Any]: return await _gis_roads()

@api.get("/public/gis/roads")
async def public_gis_roads() -> Dict[str, Any]: return await _gis_roads()

async def _gis_villages() -> Dict[str, Any]:
    villages = await repo.list_villages()
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [v["lon"], v["lat"]]}, "properties": v} for v in villages]}

@api.get("/gis/villages")
async def gis_villages() -> Dict[str, Any]: return await _gis_villages()

@api.get("/public/gis/villages")
async def public_gis_villages() -> Dict[str, Any]: return await _gis_villages()

@api.get("/gis/reports")
async def gis_reports() -> Dict[str, Any]:
    reports = await repo.list_reports(200)
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]}, "properties": r} for r in reports]}

@api.get("/gis/alerts")
async def gis_alerts() -> List[Dict[str, Any]]: return await repo.list_alerts(50)

@api.get("/public/alerts")
async def public_alerts(limit: int = 50) -> List[Dict[str, Any]]: return await repo.list_alerts(limit)

@api.get("/gis/nearby")
async def gis_nearby(lat: float, lon: float) -> Dict[str, Any]:
    return {"roads": await repo.nearest_roads(lat, lon, 3), "villages": await repo.nearest_villages(lat, lon, 3)}

# --- Shelters & safe-route guidance ------------------------------------------
# Everything a person needs to answer "where do I go?" is reachable without a
# login. Somebody standing on a moving slope must not be asked to sign in first,
# so the read paths are mirrored under /api/public/. Writes stay with AUTHORITY.

async def _gis_shelters() -> Dict[str, Any]:
    shelters = await repo.list_shelters()
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]},
         "properties": {k: v for k, v in s.items() if k not in ("lat", "lon")}}
        for s in shelters if s.get("lat") is not None and s.get("lon") is not None]}

@api.get("/gis/shelters")
async def gis_shelters() -> Dict[str, Any]:
    """Shelters as GeoJSON for the operations map."""
    return await _gis_shelters()

@api.get("/public/gis/shelters")
async def public_gis_shelters() -> Dict[str, Any]:
    """Shelters as GeoJSON for the citizen map — no sign-in."""
    return await _gis_shelters()

@api.get("/shelters")
async def list_shelters() -> List[Dict[str, Any]]:
    """Every shelter with its status and recorded occupancy."""
    return await repo.list_shelters()

@api.get("/public/shelters")
async def public_list_shelters() -> List[Dict[str, Any]]:
    """Shelter directory for citizens — no sign-in."""
    return await repo.list_shelters()

async def _safe_route(lat: float, lon: float, limit: int = 5) -> Dict[str, Any]:
    """Compose the recommendation from live shelter, road and prediction data.

    The three reads are independent, so they are gathered concurrently — this
    endpoint is on the critical path of an evacuation decision.
    """
    shelters, roads, zones = await asyncio.gather(
        repo.nearest_shelters(lat, lon, max(limit, 5)),
        repo.nearest_roads(lat, lon, 6),
        _zones_payload(),
    )
    return safe_route_service.build_recommendation(lat, lon, shelters, roads, zones, limit=limit)

@api.get("/safe-route")
async def safe_route(lat: float, lon: float, limit: int = 5) -> Dict[str, Any]:
    """Ranked shelters plus ordered movement guidance for a point."""
    return await _safe_route(lat, lon, limit)

@api.get("/public/safe-route")
async def public_safe_route(lat: float, lon: float, limit: int = 5) -> Dict[str, Any]:
    """The "where do I go?" answer, reachable without a login."""
    return await _safe_route(lat, lon, limit)

class ShelterUpsert(BaseModel):
    shelter_id: str
    name: str
    lat: float
    lon: float
    category: Optional[str] = "OTHER"
    status: Optional[str] = "OPEN"
    capacity: Optional[int] = None            # None means "not recorded", never 0
    current_occupancy: Optional[int] = None   # None means "not counted", never empty
    elevation_m: Optional[float] = None
    contact_phone: Optional[str] = None
    managed_by: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    source: Optional[str] = "AUTHORITY"

@api.post("/shelters")
async def create_shelter(s: ShelterUpsert, _=Depends(require_roles("AUTHORITY"))) -> Dict[str, Any]:
    """Register or replace a shelter record."""
    return await repo.upsert_shelter(s.model_dump())

class ShelterUpdate(BaseModel):
    status: Optional[str] = None
    capacity: Optional[int] = None
    current_occupancy: Optional[int] = None
    contact_phone: Optional[str] = None
    managed_by: Optional[str] = None

@api.patch("/shelters/{shelter_id}")
async def patch_shelter(shelter_id: str, s: ShelterUpdate, _=Depends(require_roles("FIELD_OFFICER"))) -> Dict[str, Any]:
    """Update occupancy or status. Field officers can do this — they are the ones
    standing at the gate counting people in, and a stale occupancy figure is what
    sends the next family to a full camp."""
    changes = {k: v for k, v in s.model_dump().items() if v is not None}
    if not changes: raise HTTPException(status_code=422, detail="no_shelter_changes")
    updated = await repo.update_shelter(shelter_id, changes)
    if not updated: raise HTTPException(status_code=404, detail="shelter_not_found")
    return updated

@api.get("/weather")
async def weather(latitude: float, longitude: float) -> Dict[str, Any]: return await weather_service.get_current(latitude, longitude)

@api.get("/weather/history")
async def weather_history(latitude: float, longitude: float, days: int = 30) -> Dict[str, Any]: return await weather_service.get_history(latitude, longitude, days)

@api.get("/terrain/elevation")
async def terrain_elevation(latitude: float, longitude: float) -> Dict[str, Any]: return await weather_service.get_elevation(latitude, longitude)

@api.post("/terrain/recompute")
async def terrain_recompute(zone_id: Optional[str] = None, _=Depends(require_roles("AUTHORITY"))) -> Dict[str, Any]:
    zones = [await repo.get_zone(zone_id)] if zone_id else await repo.list_zones()
    zones = [z for z in zones if z]
    c = await repo.client(); ok = failed = 0
    for zone in zones:
        try:
            t = await terrain_service.compute_dem_features(zone["centroid"]["lat"], zone["centroid"]["lon"])
            await c.table("zones").update({**t, "terrain_source": "DEM"}).eq("zone_id", zone["zone_id"]).execute()
            await c.table("terrain_data").upsert({"zone_id": zone["id"], **t, "source": "DEM", "fetched_at": datetime.now(timezone.utc).isoformat()}, on_conflict="zone_id").execute(); ok += 1
        except Exception as exc: log.warning("DEM recompute failed zone=%s reason=%s", zone.get("zone_id"), exc); failed += 1
    return {"ok": ok, "failed": failed, "source": "OPEN_METEO_ELEVATION"}

@api.get("/sensors")
async def sensors_list(status: Optional[str] = None) -> List[Dict[str, Any]]: return await repo.list_sensors(status)

class SensorReading(BaseModel):
    sensor_id: str
    measurement_type: str
    value: float

@api.post("/sensors/readings")
async def post_reading(r: SensorReading, _=Depends(require_roles("FIELD_OFFICER"))) -> Dict[str, Any]:
    try: return await repo.insert_sensor_reading(r.sensor_id, r.measurement_type, r.value)
    except ValueError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc

class ReportCreate(BaseModel):
    lat: float
    lon: float
    report_type: str
    description: Optional[str] = ""
    reporter_role: Optional[str] = None
    reporter_name: Optional[str] = None
    client_uuid: Optional[str] = None

@api.post("/reports")
async def create_report(r: ReportCreate, request: Request) -> Dict[str, Any]:
    """Accept a report from anyone signed in — including a CITIZEN.

    Citizen reports are the platform's only source of ground truth that arrives
    faster than a satellite pass, so the route is deliberately open to every
    authenticated role. What a citizen cannot do is change the world on their
    own word: only an ops role may flip a road to BLOCKED below, and every report
    lands as SUBMITTED until a human triages it.
    """
    user = request.state.supabase_user
    profile = request.state.profile
    if r.client_uuid:
        existing = await repo.find_report_by_client_uuid(r.client_uuid)
        if existing: return existing
    if r.report_type == "ROAD_BLOCKAGE":
        near = await repo.nearest_roads(r.lat, r.lon, 1)
        if near and profile["role"] in {"ADMIN", "AUTHORITY", "FIELD_OFFICER"}:
            await repo.update_road_status(near[0]["road_id"], "BLOCKED")
    zones = await repo.list_zones()
    if not zones: raise HTTPException(status_code=503, detail="no_zones_configured")
    # Great-circle nearest, not squared degrees: a degree of longitude is ~10%
    # shorter than a degree of latitude at NER's latitudes, so the flat
    # approximation can pick the wrong zone near a boundary.
    zone = min(zones, key=lambda z: safe_route_service.haversine_km(r.lat, r.lon, z["centroid"]["lat"], z["centroid"]["lon"]))
    payload = r.model_dump()
    payload.update({"reporter_id": user["id"], "reporter_role": profile["role"],
                    "reporter_name": profile.get("full_name") or user.get("email") or "User",
                    "nearest_zone_id": zone.get("id")})
    result = await repo.insert_report(payload)
    result["zone_id"] = zone["zone_id"]
    result["zone_name"] = zone.get("name")
    return result

@api.get("/reports")
async def list_reports(limit: int = 100, status: Optional[str] = None, report_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Reports with media counts, resolved zone names, and corroboration.

    Corroboration is attached per report because it is the single most useful
    thing a triaging operator can know about a claim: whether anyone else,
    independently, is saying the same thing. It is computed against the *whole*
    recent set rather than the filtered page — otherwise filtering to SUBMITTED
    would hide the very verified report that corroborates the one on screen.
    """
    rows = await repo.list_reports_enriched(limit, status, report_type)
    corpus = rows if not (status or report_type) else await repo.list_reports(max(limit, 300))
    for r in rows:
        if r.get("lat") is None or r.get("lon") is None:
            continue
        r["corroboration"] = citizen_service.corroboration(r["lat"], r["lon"], corpus)
    return rows

@api.get("/reports/summary")
async def reports_summary(limit: int = 500) -> Dict[str, Any]:
    """Triage backlog at a glance — how many claims are still unlooked-at."""
    return citizen_service.triage_summary(await repo.list_reports_enriched(limit))

@api.get("/reports/corroboration")
async def reports_corroboration(limit: int = 300, window_hours: float = citizen_service.CORROBORATION_WINDOW_HOURS) -> List[Dict[str, Any]]:
    """Zones where citizens are independently reporting the same thing.

    Only zones with at least one qualifying report are returned; a zone with no
    reports is unknown, not quiet.
    """
    reports = await repo.list_reports(limit)
    return citizen_service.zone_corroboration(await _zones_payload(), reports, window_hours=window_hours)

@api.post("/reports/{report_id}/media")
async def attach_report_media(report_id: str, media: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """Attach an uploaded photo to a report the caller is allowed to touch."""
    if not await repo.can_access_report(report_id, request.state.supabase_user["id"], request.state.profile["role"]):
        raise HTTPException(status_code=403, detail="report_media_forbidden")
    return await repo.insert_report_media(report_id, media)

@api.get("/reports/{report_id}/media")
async def get_report_media(report_id: str, request: Request) -> List[Dict[str, Any]]:
    """Signed, short-lived URLs for a report's photo evidence.

    The bucket stays private; signing happens server-side so the service-role key
    never reaches the browser.
    """
    if not await repo.can_access_report(report_id, request.state.supabase_user["id"], request.state.profile["role"]):
        raise HTTPException(status_code=403, detail="report_media_forbidden")
    return await repo.signed_media_urls(report_id)

class ReportTriage(BaseModel):
    status: str
    note: Optional[str] = ""
    incident_id: Optional[str] = None

@api.patch("/reports/{report_id}")
async def triage_report(report_id: str, t: ReportTriage, request: Request, _=Depends(require_roles("FIELD_OFFICER"))) -> Dict[str, Any]:
    """Record a human's verdict on a claim: verified, rejected, duplicate, actioned.

    Rejections are stamped just like confirmations — "someone checked and said no"
    is a finding worth keeping, and it stops a dismissed report from quietly
    re-entering the corroboration count.
    """
    try:
        patch = citizen_service.triage_patch(t.status, t.note or "", t.incident_id, request.state.supabase_user["id"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    updated = await repo.update_report(report_id, patch)
    if not updated: raise HTTPException(status_code=404, detail="report_not_found")
    return updated

class AlertCreate(BaseModel):
    zone_id: str
    severity: str
    reason: str
    recommended_action: str = "Evacuate at-risk slopes; halt construction; notify local authorities."

@api.post("/alerts")
async def create_alert(a: AlertCreate, request: Request, _=Depends(require_roles("AUTHORITY"))) -> Dict[str, Any]:
    zone = await repo.get_zone(a.zone_id)
    if not zone: raise HTTPException(status_code=404, detail="zone_not_found")
    # translations is a JSONB blob: {lang: text, ..., "_sources": {lang: provenance}}.
    # Sources ride inside the existing column so no schema migration is required.
    translations = await build_alert_translations(a.severity, zone["name"], zone["district"], zone["state"], a.reason, a.recommended_action, list(SUPPORTED_LANGUAGES.keys()))
    return await repo.create_alert({"zone_id": zone["id"], "severity": a.severity, "reason": a.reason, "recommended_action": a.recommended_action, "translations": translations, "status": "ACTIVE", "created_by": request.state.supabase_user["id"]})

@api.get("/alerts")
async def list_alerts(limit: int = 100) -> List[Dict[str, Any]]: return await repo.list_alerts(limit)

@api.get("/notifications")
async def list_notifications(limit: int = 200) -> List[Dict[str, Any]]: return await repo.list_notifications(limit)

@api.get("/notifications/status")
async def notification_status() -> Dict[str, Any]:
    configured = bool(os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON"))
    return {"provider": "FCM_HTTP_V1" if configured else "LOG_ONLY", "firebase_configured": configured}

class RecipientCreate(BaseModel):
    name: str
    phone: str
    role: str = "AUTHORITY"
    district: Optional[str] = None
    language: str = "en"

@api.post("/recipients")
async def create_recipient(r: RecipientCreate, _=Depends(require_roles("AUTHORITY"))) -> Dict[str, Any]: return await repo.create_recipient(r.model_dump())

@api.get("/recipients")
async def list_recipients(_=Depends(require_roles("AUTHORITY"))) -> List[Dict[str, Any]]: return await repo.list_recipients()

@api.delete("/recipients/{recipient_id}")
async def delete_recipient(recipient_id: str, _=Depends(require_roles("AUTHORITY"))) -> Dict[str, Any]: return {"deleted": await repo.delete_recipient(recipient_id)}

@api.get("/response/priorities")
async def response_priorities(_=Depends(require_roles("AUTHORITY"))) -> List[Dict[str, Any]]:
    predictions = await repo.get_predictions(); out = []
    for p in predictions:
        zone = await repo.get_zone(p["zone_id"])
        if not zone: continue
        priority = risk_service.classify_response_priority(p, zone)
        out.append({"zone_id": p["zone_id"], "zone_name": zone["name"], "state": zone["state"], "district": zone["district"], "severity": p.get("severity"), "risk_score": p.get("risk_score"), **priority})
    order = {"P1":0,"P2":1,"P3":2,"P4":3}; return sorted(out, key=lambda x: order.get(x["priority"],9))

@api.get("/dashboard/summary")
async def dashboard_summary() -> Dict[str, Any]: return {**await repo.dashboard_counts(), "timestamp": datetime.now(timezone.utc).isoformat()}

class ExplainRequest(BaseModel):
    severity: str
    factors: List[Dict[str, Any]]
    zone_name: str

@api.post("/explain")
async def explain(req: ExplainRequest) -> Dict[str, Any]: return {"explanation": await explain_risk(req.severity, req.factors, req.zone_name)}

@api.get("/satellite/search")
async def satellite_search(zone_id: str) -> Dict[str, Any]: return {"status":"unavailable","reason":"Copernicus credentials not configured","source":"COPERNICUS","zone_id":zone_id}

class FeedbackReq(BaseModel):
    zone_id: str
    prediction_id: Optional[str] = None
    label: str
    notes: Optional[str] = ""

@api.post("/model/feedback")
async def model_feedback(f: FeedbackReq, request: Request, _=Depends(require_roles("AUTHORITY"))) -> Dict[str, Any]:
    payload = f.model_dump()
    payload["created_by"] = request.state.supabase_user["id"]
    return await repo.create_feedback(payload)

# ---------------------------------------------------------------------------
# Feature C — Model transparency panel
# ---------------------------------------------------------------------------
@api.get("/model/transparency")
async def model_transparency() -> Dict[str, Any]:
    """What the model predicts, its operating point, and what it is NOT for.
    All numbers come from the shipped model artifacts — nothing is fabricated."""
    return ml_service.transparency()

# ---------------------------------------------------------------------------
# Feature A — Dispatch & routing (response_tasks board + route from road status)
# ---------------------------------------------------------------------------
def _build_route(nearest: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarize access to a site from the nearest road segments. Purely derived
    from stored road status — no synthetic routing/ETA is invented."""
    blocked = [r for r in nearest if r.get("status") in ("BLOCKED", "RESTRICTED")]
    return {
        "nearest_roads": [{"road_id": r.get("road_id"), "name": r.get("name"), "status": r.get("status"),
                           "distance_km": round(r.get("distance_km"), 2) if r.get("distance_km") is not None else None}
                          for r in nearest],
        "blocked_segments": [{"road_id": r.get("road_id"), "name": r.get("name"), "status": r.get("status")} for r in blocked],
        "access": "IMPACTED" if blocked else ("CLEAR" if nearest else "UNKNOWN"),
        "source": "DERIVED_FROM_ROAD_STATUS",
    }

class DispatchRequest(BaseModel):
    zone_id: str                         # app zone code, e.g. "NER-001"
    title: Optional[str] = None
    team: Optional[str] = None
    description: Optional[str] = ""

@api.post("/response/dispatch")
async def response_dispatch(req: DispatchRequest, request: Request, _=Depends(require_roles("AUTHORITY"))) -> Dict[str, Any]:
    """Create a DISPATCHED response task for a zone, attaching the nearest route
    and flagging any blocked segments on the way, plus the current P1-P4 priority."""
    zone = await repo.get_zone(req.zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="zone_not_found")
    nearest = await repo.nearest_roads(zone["centroid"]["lat"], zone["centroid"]["lon"], 5)
    route = _build_route(nearest)
    prediction = await repo.get_latest_prediction(req.zone_id)
    priority = risk_service.classify_response_priority(prediction, zone)["priority"] if prediction else None
    return await repo.create_response_task({
        "zone_code": req.zone_id,
        "title": req.title or f"Dispatch to {zone['name']}",
        "description": req.description or "",
        "status": "DISPATCHED",
        "phase": "RESPONSE",
        "team": req.team,
        "route": route,
        "priority": priority,
        "source": "AUTHORITY",
        "created_by": request.state.supabase_user["id"],
    })

class TaskCreate(BaseModel):
    zone_id: Optional[str] = None
    title: str
    description: Optional[str] = ""
    team: Optional[str] = None
    priority: Optional[str] = None
    phase: str = "RESPONSE"
    status: str = "PENDING"
    incident_id: Optional[str] = None

@api.post("/response/tasks")
async def create_task(t: TaskCreate, request: Request, _=Depends(require_roles("FIELD_OFFICER"))) -> Dict[str, Any]:
    return await repo.create_response_task({**t.model_dump(), "zone_code": t.zone_id, "created_by": request.state.supabase_user["id"]})

@api.get("/response/tasks")
async def list_tasks(phase: Optional[str] = None, status: Optional[str] = None, incident_id: Optional[str] = None) -> List[Dict[str, Any]]:
    return await repo.list_response_tasks(phase=phase, status=status, incident_id=incident_id)

class TaskUpdate(BaseModel):
    status: Optional[str] = None
    team: Optional[str] = None
    priority: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None

@api.patch("/response/tasks/{task_id}")
async def update_task(task_id: str, t: TaskUpdate, _=Depends(require_roles("FIELD_OFFICER"))) -> Dict[str, Any]:
    updated = await repo.update_response_task(task_id, t.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail="task_not_found")
    return updated

# ---------------------------------------------------------------------------
# Feature B — Live operations feed
# ---------------------------------------------------------------------------
@api.get("/ops/activity")
async def ops_activity(limit: int = 60) -> List[Dict[str, Any]]:
    return await repo.ops_activity(limit)

@api.get("/ops/summary")
async def ops_summary() -> Dict[str, Any]:
    return await repo.ops_summary()

# ---------------------------------------------------------------------------
# Feature D — Recovery module (incidents, per-village impact, relief resources)
# ---------------------------------------------------------------------------
class IncidentCreate(BaseModel):
    zone_id: Optional[str] = None
    title: str
    severity: Optional[str] = None
    summary: Optional[str] = ""
    occurred_at: Optional[str] = None

@api.post("/incidents")
async def create_incident(i: IncidentCreate, request: Request, _=Depends(require_roles("AUTHORITY"))) -> Dict[str, Any]:
    return await repo.create_incident({**i.model_dump(), "zone_code": i.zone_id, "confirmed_by": request.state.supabase_user["id"]})

@api.get("/incidents")
async def list_incidents(status: Optional[str] = None) -> List[Dict[str, Any]]:
    return await repo.list_incidents(status)

@api.get("/incidents/{incident_id}")
async def get_incident(incident_id: str) -> Dict[str, Any]:
    inc = await repo.get_incident(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="incident_not_found")
    return inc

class IncidentUpdate(BaseModel):
    status: Optional[str] = None
    severity: Optional[str] = None
    summary: Optional[str] = None
    title: Optional[str] = None

@api.patch("/incidents/{incident_id}")
async def update_incident(incident_id: str, i: IncidentUpdate, _=Depends(require_roles("AUTHORITY"))) -> Dict[str, Any]:
    updated = await repo.update_incident(incident_id, i.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail="incident_not_found")
    return updated

class ImpactCreate(BaseModel):
    village_id: Optional[str] = None
    village_name: Optional[str] = None
    affected_population: Optional[int] = None
    households: Optional[int] = None
    casualties: Optional[int] = None
    injured: Optional[int] = None
    status: str = "ASSESSING"
    needs: Optional[Dict[str, Any]] = None
    notes: Optional[str] = ""

@api.post("/incidents/{incident_id}/impacts")
async def add_impact(incident_id: str, imp: ImpactCreate, _=Depends(require_roles("FIELD_OFFICER"))) -> Dict[str, Any]:
    return await repo.create_impact({**imp.model_dump(), "incident_id": incident_id})

class ImpactUpdate(BaseModel):
    affected_population: Optional[int] = None
    households: Optional[int] = None
    casualties: Optional[int] = None
    injured: Optional[int] = None
    status: Optional[str] = None
    needs: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None

@api.patch("/impacts/{impact_id}")
async def update_impact(impact_id: str, imp: ImpactUpdate, _=Depends(require_roles("FIELD_OFFICER"))) -> Dict[str, Any]:
    updated = await repo.update_impact(impact_id, imp.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail="impact_not_found")
    return updated

class ResourceCreate(BaseModel):
    resource_type: str
    label: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    status: str = "REQUESTED"
    notes: Optional[str] = ""

@api.post("/incidents/{incident_id}/resources")
async def add_resource(incident_id: str, res: ResourceCreate, _=Depends(require_roles("AUTHORITY"))) -> Dict[str, Any]:
    return await repo.create_resource({**res.model_dump(), "incident_id": incident_id})

class ResourceUpdate(BaseModel):
    status: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    label: Optional[str] = None
    notes: Optional[str] = None

@api.patch("/resources/{resource_id}")
async def update_resource(resource_id: str, res: ResourceUpdate, _=Depends(require_roles("AUTHORITY"))) -> Dict[str, Any]:
    updated = await repo.update_resource(resource_id, res.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail="resource_not_found")
    return updated

# ---------------------------------------------------------------------------
# Feature F — Recovery Playbook (phased recovery steps per confirmed incident)
#   "What do we actually do to recover?" — a phased checklist (relief -> early
#   recovery -> restoration -> resilience) generated from a standard NDMA/Sphere-
#   aligned template, then worked step by step. Template steps are tagged
#   source=TEMPLATE, user-added steps source=MANUAL.
# ---------------------------------------------------------------------------
@api.get("/recovery/playbook")
async def recovery_playbook_template() -> Dict[str, Any]:
    """The template itself (phases + full step list) so the UI can preview what a
    plan will contain. Pure guidance content — not event data."""
    return {"framework": playbook.FRAMEWORK, "phases": playbook.phases(), "steps": playbook.build_steps("CRITICAL")}

@api.get("/recovery/overview")
async def recovery_overview(limit: int = 100) -> List[Dict[str, Any]]:
    """Cross-incident recovery status: one row per incident with its phase,
    progress and how many steps are waiting on an on-ground assessment.
    Incidents without a plan come back with plan=null — not a fabricated 0%."""
    return await repo.recovery_overview(limit=limit)

@api.post("/incidents/{incident_id}/recovery-plan")
async def gen_recovery_plan(incident_id: str, regenerate: bool = False, _=Depends(require_roles("AUTHORITY"))) -> Dict[str, Any]:
    """Generate (or top up) the recovery plan for an incident. Idempotent: never
    duplicates a step already present, never resets progress."""
    inc = await repo.get_incident(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="incident_not_found")
    return await repo.generate_recovery_plan(incident_id, inc.get("severity"), inc.get("confirmed_by"), regenerate=regenerate)

@api.get("/incidents/{incident_id}/recovery-plan")
async def read_recovery_plan(incident_id: str) -> Dict[str, Any]:
    plan = await repo.get_recovery_plan(incident_id)
    if not plan:
        raise HTTPException(status_code=404, detail="no_recovery_plan")
    return plan

class RecoveryStepCreate(BaseModel):
    phase: str = "EARLY_RECOVERY"
    title: str
    detail: Optional[str] = ""
    owner: Optional[str] = None
    requires_assessment: Optional[bool] = False   # mark a manual step as needing on-ground confirmation

@api.post("/recovery-plans/{plan_id}/steps")
async def create_recovery_step(plan_id: str, s: RecoveryStepCreate, _=Depends(require_roles("FIELD_OFFICER"))) -> Dict[str, Any]:
    return await repo.add_recovery_step(plan_id, s.model_dump())

class RecoveryStepUpdate(BaseModel):
    status: Optional[str] = None      # PENDING | IN_PROGRESS | DONE | NA
    owner: Optional[str] = None
    notes: Optional[str] = None
    due_at: Optional[str] = None
    title: Optional[str] = None
    detail: Optional[str] = None

@api.patch("/recovery-steps/{step_id}")
async def patch_recovery_step(step_id: str, s: RecoveryStepUpdate, _=Depends(require_roles("FIELD_OFFICER"))) -> Dict[str, Any]:
    updated = await repo.update_recovery_step(step_id, s.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail="step_not_found")
    return updated

# ---------------------------------------------------------------------------
# Feature G — Monitoring watchboard (improves the existing prediction/alert loop)
#   Turns stored predictions into an operational watch picture: watch levels,
#   rainfall trend and prediction freshness. Reshapes existing data only.
# ---------------------------------------------------------------------------
@api.get("/monitoring/watchboard")
async def monitoring_watchboard() -> List[Dict[str, Any]]:
    return monitoring_service.build_watchboard(await repo.get_predictions())

@api.get("/monitoring/summary")
async def monitoring_summary() -> Dict[str, Any]:
    rows = monitoring_service.build_watchboard(await repo.get_predictions())
    return monitoring_service.watchboard_summary(rows)

@api.get("/public/monitoring/watchboard")
async def public_monitoring_watchboard() -> List[Dict[str, Any]]:
    return monitoring_service.build_watchboard(await repo.get_predictions())

# ---------------------------------------------------------------------------
# Feature H — Situation report (SITREP) generator
#   One-click incident summary composed from stored records. Totals only sum
#   assessed villages and say how many are still "not assessed" — never a
#   fabricated zero.
# ---------------------------------------------------------------------------
def _sum_known(rows: List[Dict[str, Any]], key: str) -> tuple:
    vals = [r.get(key) for r in rows if r.get(key) is not None]
    return sum(vals), len(rows) - len(vals)

def _compose_sitrep(inc: Dict[str, Any]) -> Dict[str, Any]:
    imp = inc.get("impacts") or []
    res = inc.get("resources") or []
    plan = inc.get("recovery_plan") or {}
    prog = plan.get("progress") or {}
    tasks = inc.get("recovery_tasks") or []
    aff, aff_b = _sum_known(imp, "affected_population")
    homes, homes_b = _sum_known(imp, "households")
    cas, cas_b = _sum_known(imp, "casualties")
    inj, inj_b = _sum_known(imp, "injured")
    ts = datetime.now(timezone.utc).isoformat()
    def blank(n): return f"  ({n} village(s) not yet assessed)" if n else ""
    loc = ", ".join([x for x in [inc.get("zone_name"), inc.get("district"), inc.get("state")] if x])
    L = [f"# SITUATION REPORT — {inc.get('title')}",
         f"_Generated {ts} · source: platform records (no fabricated figures)_", "",
         f"- Status: **{inc.get('status')}**   Severity: **{inc.get('severity') or 'n/a'}**",
         f"- Location: {loc or 'n/a'}"]
    if inc.get("occurred_at"): L.append(f"- Occurred: {inc.get('occurred_at')}")
    if inc.get("summary"): L.append(f"- Summary: {inc.get('summary')}")
    L += ["", "## Human impact",
          f"- Villages reporting: {len(imp)}",
          f"- People affected: {aff}{blank(aff_b)}",
          f"- Households affected: {homes}{blank(homes_b)}",
          f"- Casualties: {cas}{blank(cas_b)}",
          f"- Injured: {inj}{blank(inj_b)}"]
    L += ["", "## Relief resources"]
    if res:
        for st in ("REQUESTED", "ALLOCATED", "IN_TRANSIT", "DELIVERED"):
            group = [r for r in res if r.get("status") == st]
            if group:
                items = ", ".join([f"{r.get('label') or r.get('resource_type')}" + (f" ({r.get('quantity')} {r.get('unit') or ''})".rstrip() if r.get("quantity") is not None else "") for r in group])
                L.append(f"- {st}: {items}")
    else:
        L.append("- None logged yet.")
    L += ["", "## Recovery progress"]
    if prog:
        L.append(f"- Overall: **{prog.get('overall_pct', 0)}%** ({prog.get('overall_done', 0)}/{prog.get('overall_total', 0)} steps done)")
        for ph in prog.get("phases", []):
            L.append(f"  - {ph.get('label')}: {ph.get('pct', 0)}% ({ph.get('done', 0)}/{ph.get('total', 0)})")
    else:
        L.append("- No recovery plan generated yet.")
    open_tasks = [t for t in tasks if t.get("status") not in ("RESOLVED", "CANCELLED")]
    L += ["", "## Operations",
          f"- Linked tasks: {len(tasks)} ({len(open_tasks)} open)"]
    totals = {"villages_reporting": len(imp), "people_affected": aff, "households": homes,
              "casualties": cas, "injured": inj, "villages_not_assessed": aff_b,
              "recovery_overall_pct": prog.get("overall_pct", 0) if prog else None,
              "open_tasks": len(open_tasks)}
    return {"incident_id": inc.get("id"), "generated_at": ts, "markdown": "\n".join(L), "totals": totals}

@api.get("/incidents/{incident_id}/sitrep")
async def incident_sitrep(incident_id: str) -> Dict[str, Any]:
    inc = await repo.get_incident(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="incident_not_found")
    return _compose_sitrep(inc)

app.include_router(api)

# Single CORS layer, added last so it is the OUTERMOST middleware and wraps the
# auth middleware installed above — this way preflight OPTIONS and 401/403 auth
# responses still carry CORS headers. Override the allow-list with CORS_ORIGINS
# (comma-separated). Keep exactly one CORSMiddleware in the app: a second one
# emits duplicate Access-Control-Allow-Origin headers that browsers reject.
_DEFAULT_CORS_ORIGINS = (
    "https://ner-slide-frontend-web.onrender.com,"
    "https://ner-slide-frontend-prod.onrender.com,"
    "https://ner-slide-frontend.onrender.com,"
    "http://localhost:3000"
)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[x.strip() for x in os.environ.get("CORS_ORIGINS", _DEFAULT_CORS_ORIGINS).split(",") if x.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
