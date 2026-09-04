"""Citizen report triage & corroboration (Feature J).

A citizen report is a **claim**, not a fact. This module keeps that distinction
sharp while still extracting the signal that makes citizen reporting worth
having: when several *different* people independently report the same thing in
the same place within a short window, that is strong evidence — often available
minutes before any instrument or satellite pass confirms it.

Two rules shape everything here:

1. **Distinct reporters only.** Five reports from one phone is one person being
   thorough, not five witnesses. Corroboration counts unique reporter identities,
   so a single enthusiastic user cannot manufacture a confirmation.
2. **Verification outranks volume.** One report a field officer has stood next to
   and confirmed beats twenty unchecked ones, and the signal ladder says so.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.services.safe_route_service import haversine_km

CORROBORATION_RADIUS_KM = 3.0
CORROBORATION_WINDOW_HOURS = 24.0

# Triage vocabulary. Mirrors the reports_status_check constraint in schema.sql.
STATUSES = ("SUBMITTED", "VERIFIED", "REJECTED", "DUPLICATE", "ACTIONED")
OPEN_STATUSES = ("SUBMITTED",)
# A rejected or duplicate report must never contribute to a corroboration count —
# that would let triaged-away noise keep voting.
COUNTING_STATUSES = ("SUBMITTED", "VERIFIED", "ACTIONED")

SIGNAL_SOURCE = "DERIVED_FROM_CITIZEN_REPORTS"


def _parse(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        parsed = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _within_window(report: Dict[str, Any], cutoff: datetime) -> bool:
    ts = _parse(report.get("created_at"))
    return ts is not None and ts >= cutoff


def corroboration(lat: float, lon: float, reports: Iterable[Dict[str, Any]],
                  radius_km: float = CORROBORATION_RADIUS_KM,
                  window_hours: float = CORROBORATION_WINDOW_HOURS,
                  now: Optional[datetime] = None) -> Dict[str, Any]:
    """How much independent ground truth supports a claim at this point?

    Returns the counts *and* the ladder rung they earn, with the thresholds
    published alongside so the label can be audited rather than trusted.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=window_hours)

    nearby: List[Dict[str, Any]] = []
    for r in reports or []:
        if (r.get("status") or "SUBMITTED").upper() not in COUNTING_STATUSES:
            continue
        rlat, rlon = r.get("lat"), r.get("lon")
        if rlat is None or rlon is None:
            continue
        if haversine_km(lat, lon, rlat, rlon) > radius_km:
            continue
        if not _within_window(r, cutoff):
            continue
        nearby.append(r)

    reporters = {r.get("reporter_id") for r in nearby if r.get("reporter_id")}
    anonymous = len([r for r in nearby if not r.get("reporter_id")])
    verified = [r for r in nearby if (r.get("status") or "").upper() in ("VERIFIED", "ACTIONED")]
    # Reports with no reporter_id cannot be proven distinct, so they are counted
    # once collectively rather than each being treated as a separate witness.
    distinct = len(reporters) + (1 if anonymous else 0)

    if verified:
        signal, label = "CONFIRMED", "Confirmed on the ground by a responder"
    elif distinct >= 2:
        signal, label = "CORROBORATED", f"{distinct} independent reporters say the same thing"
    elif nearby:
        signal, label = "SINGLE", "One unverified report"
    else:
        signal, label = "NONE", "No citizen reports nearby in this window"

    return {
        "signal": signal,
        "label": label,
        "reports_nearby": len(nearby),
        "distinct_reporters": distinct,
        "verified_reports": len(verified),
        "report_types": sorted({r.get("report_type") for r in nearby if r.get("report_type")}),
        "radius_km": radius_km,
        "window_hours": window_hours,
        "source": SIGNAL_SOURCE,
    }


def zone_corroboration(zones: Iterable[Dict[str, Any]], reports: Iterable[Dict[str, Any]],
                       radius_km: float = CORROBORATION_RADIUS_KM,
                       window_hours: float = CORROBORATION_WINDOW_HOURS,
                       now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Corroboration per zone, for zones that actually have any.

    Zones with no nearby reports are omitted rather than returned as zeros: an
    absence of reports is an absence of information, not evidence of calm, and a
    long list of `0`s invites the opposite reading.
    """
    reports = list(reports or [])
    out: List[Dict[str, Any]] = []
    for z in zones or []:
        centroid = z.get("centroid") or {}
        lat, lon = centroid.get("lat"), centroid.get("lon")
        if lat is None or lon is None:
            continue
        c = corroboration(lat, lon, reports, radius_km, window_hours, now)
        if c["signal"] == "NONE":
            continue
        out.append({
            "zone_id": z.get("zone_id"),
            "zone_name": z.get("name"),
            "district": z.get("district"),
            "state": z.get("state"),
            "severity": (z.get("latest") or {}).get("severity"),
            **c,
        })
    order = {"CONFIRMED": 0, "CORROBORATED": 1, "SINGLE": 2}
    out.sort(key=lambda r: (order.get(r["signal"], 9), -r["reports_nearby"]))
    return out


def triage_patch(status: str, note: str = "", incident_id: Optional[str] = None,
                 actor_id: Optional[str] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Build the column patch for a triage decision.

    `verified_at`/`verified_by` are stamped when a decision is *made* — including
    a rejection, because "someone looked at this and said no" is exactly as
    important to record as a confirmation. Returning a report to SUBMITTED clears
    the stamp so a stale decision cannot linger as if it were current.
    """
    status = (status or "").upper()
    if status not in STATUSES:
        raise ValueError(f"invalid_report_status:{status}")
    now = now or datetime.now(timezone.utc)
    patch: Dict[str, Any] = {"status": status, "verification_note": note or ""}
    if status == "SUBMITTED":
        patch.update({"verified_at": None, "verified_by": None})
    else:
        patch.update({"verified_at": now.isoformat(), "verified_by": actor_id})
    if incident_id is not None:
        patch["incident_id"] = incident_id or None
    return patch


def triage_summary(reports: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Counts by status plus how many are still waiting on a human."""
    counts = {s: 0 for s in STATUSES}
    for r in reports or []:
        s = (r.get("status") or "SUBMITTED").upper()
        counts[s] = counts.get(s, 0) + 1
    total = sum(counts.values())
    return {
        "by_status": counts,
        "total": total,
        "awaiting_triage": sum(counts.get(s, 0) for s in OPEN_STATUSES),
        "with_photo": len([r for r in (reports or []) if r.get("media_count")]),
    }
