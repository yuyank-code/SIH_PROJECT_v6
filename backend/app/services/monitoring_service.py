"""Monitoring service — turns the raw predictions the model already produces into
an operational watch picture.

The prediction model and alerting are already built; this layer adds three things
operators asked for, all derived from data the platform already stores (no new
network calls, no fabricated values):

  * watch level   WARNING / WATCH / ADVISORY / STAND-DOWN — what to actually do,
                  not just a severity band.
  * rainfall trend RISING / STEADY / FALLING — is the situation getting worse?
                  Derived from the stored rainfall features of the prediction
                  (last-3-days rain vs the earlier part of the week). Tagged
                  source DERIVED_FROM_PREDICTION_FEATURES so it is auditable.
  * staleness      is the prediction fresh enough to trust? A watch picture that
                  has gone cold is itself a risk, so we flag it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# A prediction older than this is flagged STALE on the watchboard.
STALE_AFTER_HOURS = 6.0

# severity band -> operational watch level + a plain-language cue.
_WATCH_BY_SEVERITY = {
    "CRITICAL": ("WARNING",    "Act now — evacuate and dispatch"),
    "HIGH":     ("WARNING",    "Prepare to act — pre-position teams"),
    "MEDIUM":   ("WATCH",      "Watch closely — conditions are building"),
    "LOW":      ("ADVISORY",   "Routine watch"),
    "UNKNOWN":  ("STAND_DOWN", "No current prediction"),
}


def _parse_ts(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def staleness(predicted_at: Optional[str], now: Optional[datetime] = None) -> Dict[str, Any]:
    """Age of a prediction and whether it has gone stale."""
    now = now or datetime.now(timezone.utc)
    dt = _parse_ts(predicted_at)
    if dt is None:
        return {"age_hours": None, "stale": True, "reason": "no_timestamp"}
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age = (now - dt).total_seconds() / 3600.0
    return {"age_hours": round(age, 1), "stale": age > STALE_AFTER_HOURS, "reason": None}


def rainfall_trend(features_used: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Cheap, honest rainfall trend from the prediction's own features.

    rainfall_3d is rain in the last 3 days; rainfall_7d is the last 7. The earlier
    part of the week is (7d - 3d). If the recent 3 days already carry more rain
    than the earlier 4, the slope is being loaded fast -> RISING. This uses only
    values already computed for the prediction — it invents nothing.
    """
    if not features_used:
        return {"trend": "UNKNOWN", "recent_3d_mm": None, "prior_4d_mm": None, "source": "UNAVAILABLE"}
    r3 = features_used.get("rainfall_3d")
    r7 = features_used.get("rainfall_7d")
    if r3 is None or r7 is None:
        return {"trend": "UNKNOWN", "recent_3d_mm": r3, "prior_4d_mm": None, "source": "UNAVAILABLE"}
    r3 = float(r3); prior = max(0.0, float(r7) - r3)
    if r3 <= 1.0 and prior <= 1.0:
        trend = "FALLING" if prior >= r3 else "STEADY"  # essentially dry week
    elif r3 > prior * 1.15:
        trend = "RISING"
    elif r3 < prior * 0.85:
        trend = "FALLING"
    else:
        trend = "STEADY"
    return {"trend": trend, "recent_3d_mm": round(r3, 1), "prior_4d_mm": round(prior, 1),
            "source": "DERIVED_FROM_PREDICTION_FEATURES"}


def watch_level(prediction: Optional[Dict[str, Any]], trend: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Map a prediction (+ optional trend) to an operational watch level.

    Severity sets the base level. A RISING rainfall trend escalates a MEDIUM
    WATCH up to a WARNING, because worsening rain on a watched slope is exactly
    when to lean forward. Escalation is recorded transparently in `rationale`.
    """
    sev = (prediction or {}).get("severity", "UNKNOWN") or "UNKNOWN"
    level, cue = _WATCH_BY_SEVERITY.get(sev, _WATCH_BY_SEVERITY["UNKNOWN"])
    rationale = [f"severity={sev}"]
    escalated = False
    if trend and trend.get("trend") == "RISING" and level == "WATCH":
        level, cue = "WARNING", "Escalated — rainfall rising on a watched slope"
        escalated = True
        rationale.append("rainfall_trend=RISING")
    return {"watch_level": level, "cue": cue, "escalated": escalated, "rationale": rationale}


# watchboard sort order: most urgent first.
_LEVEL_ORDER = {"WARNING": 0, "WATCH": 1, "ADVISORY": 2, "STAND_DOWN": 3}


def build_watchboard(predictions: List[Dict[str, Any]], now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """One row per predicted zone: severity, probability, watch level, rainfall
    trend and freshness. Input rows come straight from the predictions repo
    (already joined to zone name/state/district)."""
    now = now or datetime.now(timezone.utc)
    rows: List[Dict[str, Any]] = []
    for p in predictions:
        trend = rainfall_trend(p.get("features_used"))
        wl = watch_level(p, trend)
        fresh = staleness(p.get("predicted_at") or p.get("updated_at"), now)
        rows.append({
            "zone_id": p.get("zone_id"),
            "zone_name": p.get("zone_name"),
            "state": p.get("state"),
            "district": p.get("district"),
            "severity": p.get("severity", "UNKNOWN"),
            "probability": p.get("probability"),
            "risk_score": p.get("risk_score"),
            "watch_level": wl["watch_level"],
            "cue": wl["cue"],
            "escalated": wl["escalated"],
            "rationale": wl["rationale"],
            "trend": trend["trend"],
            "trend_detail": {"recent_3d_mm": trend["recent_3d_mm"], "prior_4d_mm": trend["prior_4d_mm"], "source": trend["source"]},
            "predicted_at": p.get("predicted_at"),
            "age_hours": fresh["age_hours"],
            "stale": fresh["stale"],
        })
    rows.sort(key=lambda r: (_LEVEL_ORDER.get(r["watch_level"], 9), -(r.get("probability") or 0)))
    return rows


def watchboard_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Counts by watch level plus how many zones have gone stale."""
    counts = {"WARNING": 0, "WATCH": 0, "ADVISORY": 0, "STAND_DOWN": 0}
    stale = 0
    for r in rows:
        counts[r["watch_level"]] = counts.get(r["watch_level"], 0) + 1
        if r.get("stale"):
            stale += 1
    return {"by_level": counts, "stale_zones": stale, "zones_monitored": len(rows),
            "stale_after_hours": STALE_AFTER_HOURS, "timestamp": (datetime.now(timezone.utc)).isoformat()}
