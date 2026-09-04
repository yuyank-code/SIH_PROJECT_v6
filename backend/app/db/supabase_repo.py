"""Supabase persistence repository for the Mongo -> Postgres migration."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from supabase import AsyncClient, acreate_client
from app.services.push_service import send_to_tokens
from app.data import recovery_playbook as playbook

_client: Optional[AsyncClient] = None

async def client() -> AsyncClient:
    global _client
    if _client is not None: return _client
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key: raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY are required")
    _client = await acreate_client(url, key); return _client

async def close() -> None:
    global _client
    if _client is not None:
        try: await _client.auth.sign_out()
        finally: _client = None

def _zone(row: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": row.get("id"), "zone_id": row.get("zone_id"), "name": row.get("name"), "district": row.get("district"), "state": row.get("state"), "centroid": row.get("centroid") or {}, "geometry": row.get("geometry"), "population": row.get("population"), "terrain": {k: row[k] for k in ("elevation_m", "slope_deg", "aspect_sin", "aspect_cos", "curvature_1_m") if row.get(k) is not None}, "terrain_source": row.get("terrain_source"), "road_blocked": row.get("road_blocked", False), "isolated_villages": row.get("isolated_villages", 0), "recent_field_report": row.get("recent_field_report", False), "created_at": row.get("created_at"), "updated_at": row.get("updated_at")}

async def list_zones(state: Optional[str] = None) -> List[Dict[str, Any]]:
    c = await client(); res = await c.rpc("list_zones_geojson", {"p_state": state}).execute(); return [_zone(x) for x in (res.data or [])]
async def get_zone(zone_id: str) -> Optional[Dict[str, Any]]:
    c=await client(); res=await c.rpc("get_zone_geojson",{"p_zone_id":zone_id}).execute(); return _zone(res.data[0]) if res.data else None
async def count_zones() -> int:
    c=await client(); res=await c.table("zones").select("id",count="exact").execute(); return int(res.count or 0)
async def nearest_roads(lat: float, lon: float, limit: int = 3) -> List[Dict[str, Any]]:
    c=await client(); res=await c.rpc("nearby_roads",{"p_lat":lat,"p_lon":lon,"p_limit":limit}).execute(); return [{"road_id":x["road_id"],"name":x["name"],"status":x["status"],"geometry":x["geometry"],"distance_km":x["distance_km"]} for x in (res.data or [])]
async def nearest_villages(lat: float, lon: float, limit: int = 3) -> List[Dict[str, Any]]:
    c=await client(); res=await c.rpc("nearby_villages",{"p_lat":lat,"p_lon":lon,"p_limit":limit}).execute(); return [dict(x) for x in (res.data or [])]
async def list_sensors(status: Optional[str] = None) -> List[Dict[str, Any]]:
    c=await client(); res=await c.rpc("list_sensors_geojson",{"p_status":status}).execute(); return [{"sensor_id":x["sensor_id"],"zone_id":x.get("zone_id"),"type":x["sensor_type"],"status":x["status"],"lat":x["lat"],"lon":x["lon"],"metadata":x.get("metadata") or {},"last_seen_iso":x.get("last_seen_at")} for x in (res.data or [])]
async def insert_sensor_reading(sensor_id: str, measurement_type: str, value: float) -> Dict[str, Any]:
    c=await client(); sensor=await c.table("sensors").select("id").eq("sensor_id",sensor_id).maybe_single().execute()
    if not sensor.data: raise ValueError("sensor_not_found")
    now=datetime.now(timezone.utc).isoformat(); res=await c.table("sensor_readings").insert({"sensor_id":sensor.data["id"],"measurement_type":measurement_type,"value":value,"recorded_at":now}).select("*").single().execute(); await c.table("sensors").update({"last_seen_at":now,"updated_at":now}).eq("id",sensor.data["id"]).execute(); return {"id":str(res.data["id"]),"sensor_id":sensor_id,"measurement_type":measurement_type,"value":value,"timestamp":now}
async def list_roads() -> List[Dict[str, Any]]:
    c=await client(); res=await c.rpc("list_roads_geojson").execute(); return [dict(x) for x in (res.data or [])]
async def update_road_status(road_id: str, status: str) -> None:
    c=await client(); await c.table("roads").update({"status":status,"updated_at":datetime.now(timezone.utc).isoformat()}).eq("road_id",road_id).execute()
async def list_villages() -> List[Dict[str, Any]]:
    c=await client(); res=await c.rpc("list_villages_geojson").execute(); return [dict(x) for x in (res.data or [])]
async def find_report_by_client_uuid(client_uuid: str) -> Optional[Dict[str, Any]]:
    c=await client(); res=await c.table("reports").select("*").eq("client_uuid",client_uuid).maybe_single().execute(); return res.data
async def insert_report(payload: Dict[str, Any]) -> Dict[str, Any]:
    # nearest_zone_id is persisted (it was previously computed by the caller and
    # then dropped on the floor, leaving the column and its index permanently
    # null). Without it a report cannot be tied back to the zone it corroborates.
    c=await client(); row={"client_uuid":payload.get("client_uuid"),"reporter_id":payload.get("reporter_id"),"lat":payload["lat"],"lon":payload["lon"],"report_type":payload["report_type"],"description":payload.get("description") or "","reporter_role":payload.get("reporter_role","CITIZEN"),"status":"SUBMITTED"}
    if payload.get("nearest_zone_id"): row["nearest_zone_id"]=payload["nearest_zone_id"]
    res=await c.table("reports").insert(row).select("*").single().execute(); return dict(res.data)
async def can_access_report(report_id: str, user_id: str, role: str) -> bool:
    if role in {"ADMIN","AUTHORITY","FIELD_OFFICER"}: return True
    c=await client(); res=await c.table("reports").select("id").eq("id",report_id).eq("reporter_id",user_id).maybe_single().execute(); return bool(res.data)
async def insert_report_media(report_id: str, media: Dict[str, Any]) -> Dict[str, Any]:
    c=await client(); row={"report_id":report_id,"storage_path":media["storage_path"],"media_type":media.get("media_type","PHOTO"),"mime_type":media.get("mime_type"),"size_bytes":media.get("size_bytes")}; res=await c.table("report_media").insert(row).select("*").single().execute(); return dict(res.data)
async def list_reports(limit: int = 100, status: Optional[str] = None, report_type: Optional[str] = None) -> List[Dict[str, Any]]:
    c=await client(); q=c.table("reports").select("*")
    if status: q=q.eq("status",status)
    if report_type: q=q.eq("report_type",report_type)
    res=await q.order("created_at",desc=True).limit(limit).execute(); return [dict(x) for x in (res.data or [])]

# ---- Citizen report triage & evidence (Feature J) --------------------------
async def list_reports_enriched(limit: int = 100, status: Optional[str] = None, report_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Reports plus the zone they fall in and how many photos they carry.

    Media and zone names are fetched in two bulk queries keyed on the page of
    reports, never one query per row.
    """
    rows = await list_reports(limit, status, report_type)
    if not rows: return []
    c = await client()
    ids = [r["id"] for r in rows]
    media_res = await c.table("report_media").select("id,report_id,storage_path,media_type,mime_type,created_at").in_("report_id", ids).execute()
    by_report: Dict[str, List[Dict[str, Any]]] = {}
    for m in (media_res.data or []): by_report.setdefault(m["report_id"], []).append(dict(m))
    zone_uuids = [r["nearest_zone_id"] for r in rows if r.get("nearest_zone_id")]
    zone_names: Dict[str, Dict[str, Any]] = {}
    if zone_uuids:
        z_res = await c.table("zones").select("id,zone_id,name,district,state").in_("id", list(set(zone_uuids))).execute()
        zone_names = {z["id"]: dict(z) for z in (z_res.data or [])}
    for r in rows:
        media = by_report.get(r["id"], [])
        r["media"] = media
        r["media_count"] = len(media)
        z = zone_names.get(r.get("nearest_zone_id")) if r.get("nearest_zone_id") else None
        # zone_id stays null when the report predates the nearest_zone_id fix —
        # an unknown zone must not be rendered as if it were assessed.
        r["zone_id"] = z["zone_id"] if z else None
        r["zone_name"] = z["name"] if z else None
        r["district"] = z.get("district") if z else None
    return rows

async def get_report(report_id: str) -> Optional[Dict[str, Any]]:
    c=await client(); res=await c.table("reports").select("*").eq("id",report_id).maybe_single().execute(); return dict(res.data) if res.data else None

async def update_report(report_id: str, changes: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    allowed={"status","verification_note","verified_at","verified_by","incident_id","description"}
    patch={k:v for k,v in changes.items() if k in allowed}
    if not patch: return await get_report(report_id)
    patch["updated_at"]=datetime.now(timezone.utc).isoformat()
    c=await client(); res=await c.table("reports").update(patch).eq("id",report_id).select("*").maybe_single().execute()
    return dict(res.data) if res.data else None

async def list_report_media(report_id: str) -> List[Dict[str, Any]]:
    c=await client(); res=await c.table("report_media").select("*").eq("report_id",report_id).order("created_at",desc=False).execute(); return [dict(x) for x in (res.data or [])]

async def signed_media_urls(report_id: str, expires_in: int = 600) -> List[Dict[str, Any]]:
    """Short-lived signed URLs for a report's photos.

    The `report-media` bucket is private. Signing happens here, on the server,
    with the service-role key — the key itself is never handed to the browser,
    only the time-limited URL it produces. A path that cannot be signed is
    returned with url=None rather than being dropped, so a broken attachment is
    visible instead of silently missing.
    """
    out: List[Dict[str, Any]] = []
    c = await client()
    for m in await list_report_media(report_id):
        url = None
        try:
            signed = await c.storage.from_("report-media").create_signed_url(m["storage_path"], expires_in)
            url = (signed or {}).get("signedURL") or (signed or {}).get("signedUrl") or (signed or {}).get("signed_url")
        except Exception:  # noqa: BLE001 - a missing object must not fail the whole page
            url = None
        out.append({**m, "url": url, "expires_in": expires_in})
    return out

# ---- Shelters (Feature K) -------------------------------------------------
async def nearest_shelters(lat: float, lon: float, limit: int = 5) -> List[Dict[str, Any]]:
    c=await client(); res=await c.rpc("nearby_shelters",{"p_lat":lat,"p_lon":lon,"p_limit":limit}).execute(); return [dict(x) for x in (res.data or [])]
async def list_shelters() -> List[Dict[str, Any]]:
    c=await client(); res=await c.rpc("list_shelters_geojson").execute(); return [dict(x) for x in (res.data or [])]
async def get_shelter(shelter_id: str) -> Optional[Dict[str, Any]]:
    c=await client(); res=await c.table("shelters").select("*").eq("shelter_id",shelter_id).maybe_single().execute(); return dict(res.data) if res.data else None
async def upsert_shelter(payload: Dict[str, Any]) -> Dict[str, Any]:
    c=await client(); row={k:v for k,v in payload.items() if k in {"shelter_id","name","category","elevation_m","capacity","current_occupancy","status","contact_phone","managed_by","district","state","source","metadata"} and v is not None}
    if payload.get("lat") is not None and payload.get("lon") is not None:
        row["location"]=f"POINT({payload['lon']} {payload['lat']})"
    row["verified_at"]=datetime.now(timezone.utc).isoformat()
    res=await c.table("shelters").upsert(row,on_conflict="shelter_id").select("*").single().execute(); return dict(res.data)
async def update_shelter(shelter_id: str, changes: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    allowed={"name","category","capacity","current_occupancy","status","contact_phone","managed_by","district","state","elevation_m"}
    patch={k:v for k,v in changes.items() if k in allowed and v is not None}
    if not patch: return await get_shelter(shelter_id)
    # An occupancy or status update is itself a human confirming the record.
    patch["verified_at"]=datetime.now(timezone.utc).isoformat()
    c=await client(); res=await c.table("shelters").update(patch).eq("shelter_id",shelter_id).select("*").maybe_single().execute()
    return dict(res.data) if res.data else None
async def create_alert(payload: Dict[str, Any]) -> Dict[str, Any]:
    c=await client(); alert=dict((await c.table("alerts").insert(payload).select("*").single().execute()).data)
    devices=await c.table("user_devices").select("user_id,fcm_token").eq("is_active",True).execute()
    tokens=[x["fcm_token"] for x in (devices.data or []) if x.get("fcm_token")]
    title=f"{alert['severity']} landslide alert"
    body=payload.get("reason") or "New landslide risk alert"
    data={"alert_id":str(alert["id"]),"severity":str(alert["severity"]),"zone_id":str(alert.get("zone_id") or "")}
    if tokens and os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON"):
        delivery=await send_to_tokens(tokens,title,body,data)
        for device in devices.data or []:
            if device.get("fcm_token"):
                status="SENT" if device["fcm_token"] in tokens and delivery["failed"] < len(tokens) else "FAILED"
                await c.table("notifications").insert({"user_id":device.get("user_id"),"alert_id":alert["id"],"channel":"PUSH","status":status,"provider":"FCM_HTTP_V1","payload":data,"sent_at":datetime.now(timezone.utc).isoformat() if status=="SENT" else None}).execute()
    return alert
async def list_alerts(limit: int = 100) -> List[Dict[str, Any]]:
    c=await client(); res=await c.table("alerts").select("*").order("created_at",desc=True).limit(limit).execute(); return [dict(x) for x in (res.data or [])]
async def list_notifications(limit: int = 200) -> List[Dict[str, Any]]:
    c=await client(); res=await c.table("notifications").select("*").order("created_at",desc=True).limit(limit).execute(); return [dict(x) for x in (res.data or [])]
async def create_notification(payload: Dict[str, Any]) -> Dict[str, Any]:
    c=await client(); res=await c.table("notifications").insert(payload).select("*").single().execute(); return dict(res.data)
async def list_active_device_tokens() -> List[Dict[str, Any]]:
    c=await client(); res=await c.table("user_devices").select("user_id,fcm_token,platform").eq("is_active",True).execute(); return [dict(x) for x in (res.data or [])]
async def deactivate_device_token(token: str) -> None:
    c=await client(); await c.table("user_devices").update({"is_active":False}).eq("fcm_token",token).execute()
async def create_recipient(payload: Dict[str, Any]) -> Dict[str, Any]:
    c=await client(); res=await c.table("recipients").insert(payload).select("*").single().execute(); return dict(res.data)
async def list_recipients() -> List[Dict[str, Any]]:
    c=await client(); res=await c.table("recipients").select("*").order("created_at",desc=True).execute(); return [dict(x) for x in (res.data or [])]
async def delete_recipient(recipient_id: str) -> int:
    c=await client(); res=await c.table("recipients").delete().eq("id",recipient_id).execute(); return len(res.data or [])
async def get_predictions() -> List[Dict[str, Any]]:
    c=await client(); res=await c.table("risk_predictions").select("*,zones!inner(zone_id,name,state,district,population,road_blocked,isolated_villages,recent_field_report)").order("predicted_at",desc=True).execute(); out=[]
    for x in res.data or []:
        z=x.pop("zones",{}) or {}; x["zone_id"]=z.get("zone_id"); x["zone_name"]=z.get("name"); x["state"]=z.get("state"); x["district"]=z.get("district"); out.append(x)
    return out
async def get_latest_prediction(zone_id: str) -> Optional[Dict[str, Any]]:
    c=await client(); zone=await c.table("zones").select("id,zone_id").eq("zone_id",zone_id).maybe_single().execute()
    if not zone.data:return None
    res=await c.table("risk_predictions").select("*").eq("zone_id",zone.data["id"]).order("predicted_at",desc=True).limit(1).maybe_single().execute()
    if not res.data:return None
    row=dict(res.data); row["zone_id"]=zone_id; return row
async def upsert_prediction(zone_id: str, result: Dict[str, Any], priority: Dict[str, Any]) -> Dict[str, Any]:
    c=await client(); zone=await c.table("zones").select("id").eq("zone_id",zone_id).single().execute(); row={"zone_id":zone.data["id"],"probability":result["probability"],"risk_score":result["risk_score"],"prediction":result["prediction"],"severity":result["severity"],"priority":priority["priority"],"model_version":result["model_version"],"features_used":result.get("features_used") or {},"contributing_factors":result.get("contributing_factors") or [],"source_map":result.get("source_map") or {},"predicted_at":result.get("timestamp") or datetime.now(timezone.utc).isoformat()}; res=await c.table("risk_predictions").upsert(row,on_conflict="zone_id").select("*").single().execute(); out=dict(res.data); out["zone_id"]=zone_id; out["response_priority"]=priority; return out
async def create_feedback(payload: Dict[str, Any]) -> Dict[str, Any]:
    c=await client(); zone=await c.table("zones").select("id").eq("zone_id",payload["zone_id"]).single().execute(); row={"zone_id":zone.data["id"],"label":payload["label"],"notes":payload.get("notes") or "","created_by":payload.get("created_by")};
    if payload.get("prediction_id"): row["prediction_id"]=payload["prediction_id"]
    res=await c.table("model_feedback").insert(row).select("*").single().execute(); return dict(res.data)
async def dashboard_counts() -> Dict[str, Any]:
    c=await client(); zones=await c.table("zones").select("id",count="exact").execute(); sensors=await list_sensors(); roads=await list_roads(); preds=await get_predictions(); alerts=await c.table("alerts").select("id",count="exact").eq("status","ACTIVE").execute(); reports=await c.table("reports").select("id",count="exact").eq("status","SUBMITTED").execute(); sev={"LOW":0,"MEDIUM":0,"HIGH":0,"CRITICAL":0,"UNKNOWN":0}
    for p in preds: sev[p.get("severity","UNKNOWN")]=sev.get(p.get("severity","UNKNOWN"),0)+1
    return {"zones_total":int(zones.count or 0),"zones_predicted":len(preds),"severity_counts":sev,"sensors_online":sum(s.get("status")=="ONLINE" for s in sensors),"sensors_offline":sum(s.get("status")=="OFFLINE" for s in sensors),"roads_blocked":sum(r.get("status")=="BLOCKED" for r in roads),"roads_at_risk":sum(r.get("status")=="RESTRICTED" for r in roads),"active_alerts":int(alerts.count or 0),"pending_reports":int(reports.count or 0)}

# ===========================================================================
# Response & Recovery (Features A/B/D)
#   response_tasks is reused for both phases via `phase` (RESPONSE|RECOVERY).
#   Every write carries a `source` so provenance is always auditable.
# ===========================================================================

async def _zone_uuid(zone_id: str) -> Optional[str]:
    """Map an app zone_id ('NER-001') to the internal zones.id UUID."""
    c=await client(); res=await c.table("zones").select("id").eq("zone_id",zone_id).maybe_single().execute()
    return res.data["id"] if res.data else None

def _task(row: Dict[str, Any]) -> Dict[str, Any]:
    z=row.pop("zones",None) or {}
    row["zone_code"]=z.get("zone_id"); row["zone_name"]=z.get("name"); row["state"]=z.get("state"); row["district"]=z.get("district")
    return row

async def create_response_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create a dispatch/recovery task. `payload['zone_code']` is the app zone_id."""
    c=await client()
    zone_uuid=await _zone_uuid(payload["zone_code"]) if payload.get("zone_code") else None
    row={
        "zone_id":zone_uuid,
        "title":payload.get("title") or "Response task",
        "description":payload.get("description") or "",
        "status":payload.get("status") or "PENDING",
        "priority":payload.get("priority"),
        "phase":payload.get("phase") or "RESPONSE",
        "team":payload.get("team"),
        "route":payload.get("route") or {},
        "incident_id":payload.get("incident_id"),
        "source":payload.get("source") or "AUTHORITY",
        "created_by":payload.get("created_by"),
    }
    res=await c.table("response_tasks").insert(row).select("*,zones(zone_id,name,state,district)").single().execute()
    return _task(dict(res.data))

async def list_response_tasks(phase: Optional[str] = None, status: Optional[str] = None, incident_id: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
    c=await client(); q=c.table("response_tasks").select("*,zones(zone_id,name,state,district)")
    if phase: q=q.eq("phase",phase)
    if status: q=q.eq("status",status)
    if incident_id: q=q.eq("incident_id",incident_id)
    res=await q.order("created_at",desc=True).limit(limit).execute()
    return [_task(dict(x)) for x in (res.data or [])]

_TASK_STATES={"PENDING","DISPATCHED","EN_ROUTE","ON_SITE","RESOLVED","CANCELLED","OPEN"}

async def update_response_task(task_id: str, changes: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    c=await client(); patch: Dict[str, Any]={}
    for k in ("status","priority","team","description","title","assigned_to"):
        if changes.get(k) is not None: patch[k]=changes[k]
    if patch.get("status")=="RESOLVED": patch["resolved_at"]=datetime.now(timezone.utc).isoformat()
    if not patch: return await get_response_task(task_id)
    res=await c.table("response_tasks").update(patch).eq("id",task_id).select("*,zones(zone_id,name,state,district)").maybe_single().execute()
    return _task(dict(res.data)) if res.data else None

async def get_response_task(task_id: str) -> Optional[Dict[str, Any]]:
    c=await client(); res=await c.table("response_tasks").select("*,zones(zone_id,name,state,district)").eq("id",task_id).maybe_single().execute()
    return _task(dict(res.data)) if res.data else None

# ---- Incidents -------------------------------------------------------------
def _incident(row: Dict[str, Any]) -> Dict[str, Any]:
    z=row.pop("zones",None) or {}
    row["zone_code"]=z.get("zone_id"); row["zone_name"]=z.get("name"); row["state"]=z.get("state"); row["district"]=z.get("district")
    return row

async def create_incident(payload: Dict[str, Any]) -> Dict[str, Any]:
    c=await client()
    zone_uuid=await _zone_uuid(payload["zone_code"]) if payload.get("zone_code") else None
    row={
        "zone_id":zone_uuid,
        "title":payload.get("title") or "Landslide incident",
        "status":payload.get("status") or "ACTIVE",
        "severity":payload.get("severity"),
        "occurred_at":payload.get("occurred_at") or datetime.now(timezone.utc).isoformat(),
        "summary":payload.get("summary") or "",
        "source":payload.get("source") or "FIELD_CONFIRMED",
        "confirmed_by":payload.get("confirmed_by"),
    }
    res=await c.table("incidents").insert(row).select("*,zones(zone_id,name,state,district)").single().execute()
    return _incident(dict(res.data))

async def list_incidents(status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    c=await client(); q=c.table("incidents").select("*,zones(zone_id,name,state,district)")
    if status: q=q.eq("status",status)
    res=await q.order("occurred_at",desc=True).limit(limit).execute()
    return [_incident(dict(x)) for x in (res.data or [])]

async def get_incident(incident_id: str) -> Optional[Dict[str, Any]]:
    c=await client(); res=await c.table("incidents").select("*,zones(zone_id,name,state,district)").eq("id",incident_id).maybe_single().execute()
    if not res.data: return None
    inc=_incident(dict(res.data))
    inc["impacts"]=await list_impacts(incident_id)
    inc["resources"]=await list_resources(incident_id)
    inc["recovery_tasks"]=await list_response_tasks(incident_id=incident_id)
    inc["recovery_plan"]=await get_recovery_plan(incident_id)
    return inc

async def update_incident(incident_id: str, changes: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    c=await client(); patch={k:changes[k] for k in ("status","severity","summary","title") if changes.get(k) is not None}
    if not patch: return await get_incident(incident_id)
    res=await c.table("incidents").update(patch).eq("id",incident_id).select("*,zones(zone_id,name,state,district)").maybe_single().execute()
    return _incident(dict(res.data)) if res.data else None

# ---- Per-village impact / needs assessment --------------------------------
async def create_impact(payload: Dict[str, Any]) -> Dict[str, Any]:
    c=await client()
    row={
        "incident_id":payload["incident_id"],
        "village_id":payload.get("village_id"),
        "village_name":payload.get("village_name"),
        "affected_population":payload.get("affected_population"),
        "households":payload.get("households"),
        "casualties":payload.get("casualties"),
        "injured":payload.get("injured"),
        "status":payload.get("status") or "ASSESSING",
        "needs":payload.get("needs") or {},
        "notes":payload.get("notes") or "",
        "source":payload.get("source") or "FIELD_REPORT",
    }
    res=await c.table("incident_impacts").insert(row).select("*").single().execute()
    return dict(res.data)

async def list_impacts(incident_id: str) -> List[Dict[str, Any]]:
    c=await client(); res=await c.table("incident_impacts").select("*").eq("incident_id",incident_id).order("created_at",desc=True).execute()
    return [dict(x) for x in (res.data or [])]

async def update_impact(impact_id: str, changes: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    c=await client(); patch={k:changes[k] for k in ("affected_population","households","casualties","injured","status","needs","notes") if changes.get(k) is not None}
    if not patch: return None
    res=await c.table("incident_impacts").update(patch).eq("id",impact_id).select("*").maybe_single().execute()
    return dict(res.data) if res.data else None

# ---- Relief resources ------------------------------------------------------
async def create_resource(payload: Dict[str, Any]) -> Dict[str, Any]:
    c=await client()
    row={
        "incident_id":payload["incident_id"],
        "resource_type":payload["resource_type"],
        "label":payload.get("label"),
        "quantity":payload.get("quantity"),
        "unit":payload.get("unit"),
        "status":payload.get("status") or "REQUESTED",
        "source":payload.get("source") or "AUTHORITY",
        "notes":payload.get("notes") or "",
    }
    res=await c.table("relief_resources").insert(row).select("*").single().execute()
    return dict(res.data)

async def list_resources(incident_id: str) -> List[Dict[str, Any]]:
    c=await client(); res=await c.table("relief_resources").select("*").eq("incident_id",incident_id).order("created_at",desc=True).execute()
    return [dict(x) for x in (res.data or [])]

async def update_resource(resource_id: str, changes: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    c=await client(); patch={k:changes[k] for k in ("status","quantity","unit","label","notes") if changes.get(k) is not None}
    if not patch: return None
    res=await c.table("relief_resources").update(patch).eq("id",resource_id).select("*").maybe_single().execute()
    return dict(res.data) if res.data else None

# ---- Live operations feed (Feature B) -------------------------------------
async def _blocked_roads() -> List[Dict[str, Any]]:
    c=await client(); res=await c.table("roads").select("road_id,name,status,updated_at").in_("status",["BLOCKED","RESTRICTED"]).order("updated_at",desc=True).execute()
    return [dict(x) for x in (res.data or [])]

async def ops_activity(limit: int = 60) -> List[Dict[str, Any]]:
    """Merge alerts, dispatch tasks, incidents, field reports and road closures
    into one timestamped feed. Pure composition of existing tables — no new
    storage. Each event is tagged with its `kind` and `source`."""
    events: List[Dict[str, Any]] = []
    for a in await list_alerts(30):
        events.append({"kind":"ALERT","ts":a.get("created_at"),"severity":a.get("severity"),
                       "title":f"{a.get('severity')} alert issued","detail":a.get("reason") or "","ref_id":a.get("id"),"source":"AUTHORITY"})
    for t in await list_response_tasks(limit=40):
        events.append({"kind":"RESPONSE_TASK","ts":t.get("updated_at") or t.get("created_at"),"severity":None,
                       "title":f"{t.get('phase','RESPONSE').title()} task {t.get('status')}: {t.get('title')}",
                       "detail":f"{t.get('zone_name') or ''} · team {t.get('team') or '—'}","ref_id":t.get("id"),"source":t.get("source") or "AUTHORITY"})
    for i in await list_incidents(limit=20):
        events.append({"kind":"INCIDENT","ts":i.get("occurred_at") or i.get("created_at"),"severity":i.get("severity"),
                       "title":f"Incident {i.get('status')}: {i.get('title')}","detail":f"{i.get('zone_name') or ''} ({i.get('district') or ''})","ref_id":i.get("id"),"source":i.get("source") or "FIELD_CONFIRMED"})
    for r in await list_reports(30):
        events.append({"kind":"REPORT","ts":r.get("created_at"),"severity":None,
                       "title":f"Field report: {r.get('report_type')}","detail":(r.get('description') or '')[:120],"ref_id":r.get("id"),"source":f"REPORTER:{r.get('reporter_role','CITIZEN')}"})
    for rd in await _blocked_roads():
        events.append({"kind":"ROAD","ts":rd.get("updated_at"),"severity":None,
                       "title":f"Road {rd.get('status')}: {rd.get('name') or rd.get('road_id')}","detail":"access impact","ref_id":rd.get("road_id"),"source":"ROAD_STATUS"})
    events=[e for e in events if e.get("ts")]
    events.sort(key=lambda e: e["ts"], reverse=True)
    return events[:limit]

async def ops_summary() -> Dict[str, Any]:
    c=await client()
    active_incidents=await c.table("incidents").select("id",count="exact").eq("status","ACTIVE").execute()
    open_tasks=await c.table("response_tasks").select("id",count="exact").not_.in_("status",["RESOLVED","CANCELLED"]).execute()
    base=await dashboard_counts()
    return {**base,
            "active_incidents":int(active_incidents.count or 0),
            "open_tasks":int(open_tasks.count or 0),
            "timestamp":datetime.now(timezone.utc).isoformat()}

# ---- Recovery playbook (Feature F) ----------------------------------------
#   A phased recovery plan per incident. Steps start life as TEMPLATE rows copied
#   from app.data.recovery_playbook; users work them and may add MANUAL steps.
#   Generating a plan is idempotent — codes already present are never duplicated
#   and progress is never reset.
_STEP_STATES = {"PENDING", "IN_PROGRESS", "DONE", "NA"}

def _recovery_progress(steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Per-phase and overall completion. Steps marked NA are excluded from the
    denominator (they do not apply to this event), never counted as done."""
    meta = playbook.phases()
    by_phase = {p["key"]: {"phase": p["key"], "label": p["label"], "window": p["window"],
                           "total": 0, "done": 0, "in_progress": 0, "na": 0} for p in meta}
    o_done = o_total = 0
    for s in steps:
        ph = by_phase.setdefault(s.get("phase"), {"phase": s.get("phase"), "label": s.get("phase"),
                                                  "window": "", "total": 0, "done": 0, "in_progress": 0, "na": 0})
        st = s.get("status")
        if st == "NA":
            ph["na"] += 1; continue
        ph["total"] += 1; o_total += 1
        if st == "DONE": ph["done"] += 1; o_done += 1
        elif st == "IN_PROGRESS": ph["in_progress"] += 1
    for ph in by_phase.values():
        ph["pct"] = round(100 * ph["done"] / ph["total"]) if ph["total"] else 0
    return {"phases": [by_phase[p["key"]] for p in meta],
            "overall_pct": round(100 * o_done / o_total) if o_total else 0,
            "overall_done": o_done, "overall_total": o_total}

async def list_recovery_steps(plan_id: str) -> List[Dict[str, Any]]:
    c=await client(); res=await c.table("recovery_steps").select("*").eq("plan_id",plan_id).order("phase_order").order("step_order").execute()
    return [dict(x) for x in (res.data or [])]

def _current_phase(progress: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The earliest phase that still has unfinished work — 'where recovery is
    right now'. None once every phase with steps is complete."""
    for ph in progress.get("phases", []):
        if ph.get("total", 0) and ph.get("done", 0) < ph["total"]:
            return {"phase": ph["phase"], "label": ph["label"], "window": ph["window"], "pct": ph["pct"]}
    return None

async def recovery_overview(limit: int = 100) -> List[Dict[str, Any]]:
    """One row per incident showing where its recovery stands — the cross-incident
    view the per-incident page cannot give. Bulk-fetches plans and steps (no N+1)
    and reuses _recovery_progress, so the numbers match the detail page exactly.
    Incidents with no plan are returned with plan=None (never a fabricated 0%)."""
    c=await client()
    incidents=await list_incidents(limit=limit)
    if not incidents: return []
    ids=[i["id"] for i in incidents]
    plans=[dict(x) for x in ((await c.table("recovery_plans").select("*").in_("incident_id",ids).execute()).data or [])]
    steps=[]
    if plans:
        plan_ids=[p["id"] for p in plans]
        steps=[dict(x) for x in ((await c.table("recovery_steps").select("*").in_("plan_id",plan_ids).execute()).data or [])]
    by_plan: Dict[str, List[Dict[str, Any]]] = {}
    for s in steps: by_plan.setdefault(s.get("plan_id"), []).append(s)
    plan_by_incident={p.get("incident_id"): p for p in plans}
    out: List[Dict[str, Any]] = []
    for inc in incidents:
        row={k: inc.get(k) for k in ("id","title","status","severity","zone_code","zone_name","district","state","occurred_at","source")}
        row["incident_id"]=inc.get("id")
        p=plan_by_incident.get(inc.get("id"))
        if not p:
            row["plan"]=None
        else:
            rows=by_plan.get(p["id"], [])
            prog=_recovery_progress(rows)
            row["plan"]={"id":p["id"],"status":p.get("status"),"framework":p.get("framework"),
                         "progress":prog,"current_phase":_current_phase(prog),
                         # steps that cannot honestly be closed from a desk yet
                         "awaiting_assessment":len([s for s in rows if s.get("requires_assessment")
                                                    and s.get("status") in ("PENDING","IN_PROGRESS")]),
                         "in_progress":len([s for s in rows if s.get("status")=="IN_PROGRESS"]),
                         "updated_at":p.get("updated_at")}
        out.append(row)
    return out

async def get_recovery_plan(incident_id: str) -> Optional[Dict[str, Any]]:
    c=await client(); res=await c.table("recovery_plans").select("*").eq("incident_id",incident_id).maybe_single().execute()
    if not res.data: return None
    plan=dict(res.data); plan["steps"]=await list_recovery_steps(plan["id"]); plan["progress"]=_recovery_progress(plan["steps"])
    return plan

async def generate_recovery_plan(incident_id: str, severity: Optional[str], created_by: Optional[str], regenerate: bool = False) -> Dict[str, Any]:
    """Create the plan if absent, then add any template steps (by code) that are
    not already present. Safe to call repeatedly: existing steps and their status
    are left untouched — only missing codes are inserted.

    The top-up always runs, which is what makes the UI's "Sync steps" button
    meaningful: if an incident is later upgraded (say MEDIUM -> CRITICAL), the
    steps that severity unlocks appear without disturbing completed work. The
    `regenerate` flag is accepted for API compatibility; there is deliberately no
    destructive path, because resetting a worked checklist would lose real
    field progress."""
    c=await client()
    existing=await c.table("recovery_plans").select("*").eq("incident_id",incident_id).maybe_single().execute()
    if existing.data:
        plan_row=dict(existing.data)
    else:
        plan_row=dict((await c.table("recovery_plans").insert({"incident_id":incident_id,"framework":playbook.FRAMEWORK,"status":"ACTIVE","created_by":created_by}).select("*").single().execute()).data)
    have={s["code"] for s in await list_recovery_steps(plan_row["id"])}
    new_rows=[{"plan_id":plan_row["id"],"code":t["code"],"phase":t["phase"],"title":t["title"],"detail":t["detail"],
               "requires_assessment":t.get("requires_assessment",False),"manageable_when":t.get("manageable_when",""),
               "status":"PENDING","phase_order":t["phase_order"],"step_order":t["step_order"],"source":"TEMPLATE"}
              for t in playbook.build_steps(severity) if t["code"] not in have]
    if new_rows: await c.table("recovery_steps").insert(new_rows).execute()
    return await get_recovery_plan(incident_id)

async def add_recovery_step(plan_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    c=await client()
    phase=payload.get("phase") or "EARLY_RECOVERY"
    order_map={p["key"]:i for i,p in enumerate(playbook.phases())}
    existing=await list_recovery_steps(plan_id)
    max_in_phase=max([s.get("step_order",0) for s in existing if s.get("phase")==phase] or [900])
    row={"plan_id":plan_id,"code":payload.get("code") or f"MANUAL-{uuid.uuid4().hex[:8]}","phase":phase,
         "title":payload.get("title") or "Custom recovery step","detail":payload.get("detail") or "",
         "requires_assessment":bool(payload.get("requires_assessment",False)),
         "manageable_when":payload.get("manageable_when",""),
         "status":payload.get("status") or "PENDING","owner":payload.get("owner"),
         "phase_order":order_map.get(phase,1),"step_order":max_in_phase+1,"source":"MANUAL"}
    res=await c.table("recovery_steps").insert(row).select("*").single().execute()
    return dict(res.data)

async def update_recovery_step(step_id: str, changes: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    c=await client(); patch={k:changes[k] for k in ("status","owner","notes","due_at","title","detail") if changes.get(k) is not None}
    if not patch: return None
    if patch.get("status")=="DONE": patch["done_at"]=datetime.now(timezone.utc).isoformat()
    elif "status" in patch: patch["done_at"]=None
    res=await c.table("recovery_steps").update(patch).eq("id",step_id).select("*").maybe_single().execute()
    return dict(res.data) if res.data else None
