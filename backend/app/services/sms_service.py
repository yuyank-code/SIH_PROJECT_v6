"""Notification service — SMS + push abstraction.

Sends SMS via Twilio when TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN /
TWILIO_FROM_NUMBER are configured. Otherwise operates in LOG_ONLY mode —
messages are recorded in the Supabase `notifications` table with status
`log_only` so the demo still shows exactly what would have been sent.

Recipients are stored in the `recipients` table with fields:
    id, name, phone, role (AUTHORITY / FIELD_OFFICER / CITIZEN),
    district (optional), language (default 'en').
"""
from __future__ import annotations

import base64
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger("sms")

_TWILIO_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"


def _twilio_configured() -> bool:
    return bool(
        os.environ.get("TWILIO_ACCOUNT_SID")
        and os.environ.get("TWILIO_AUTH_TOKEN")
        and os.environ.get("TWILIO_FROM_NUMBER")
    )


async def send_sms(phone: str, body: str) -> Dict[str, Any]:
    if not _twilio_configured():
        return {
            "status": "log_only",
            "reason": "Twilio credentials not configured",
            "phone": phone,
            "body": body,
        }
    sid = os.environ["TWILIO_ACCOUNT_SID"]
    tok = os.environ["TWILIO_AUTH_TOKEN"]
    frm = os.environ["TWILIO_FROM_NUMBER"]
    auth = base64.b64encode(f"{sid}:{tok}".encode()).decode()
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            _TWILIO_URL.format(sid=sid),
            headers={"Authorization": f"Basic {auth}"},
            data={"From": frm, "To": phone, "Body": body[:1500]},
        )
    if 200 <= r.status_code < 300:
        return {"status": "sent", "phone": phone, "sid": r.json().get("sid")}
    return {"status": "failed", "phone": phone, "http": r.status_code, "detail": r.text[:200]}


async def blast_alert(
    db,
    alert: Dict[str, Any],
    zone: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Send the alert to all matching recipients using their preferred language.

    Matching: recipient.district == zone.district OR recipient.district is None
    (nation-wide subscribers).
    """
    q_or = [{"district": zone.get("district")}, {"district": None}, {"district": ""}]
    recipients = [r async for r in db.recipients.find({"$or": q_or})]
    results: List[Dict[str, Any]] = []
    for r in recipients:
        lang = r.get("language") or "en"
        body = (alert.get("translations") or {}).get(lang) or alert.get("translations", {}).get("en") or alert.get("reason", "")
        res = await send_sms(r["phone"], body)
        rec: Dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "alert_id": alert.get("id"),
            "zone_id": zone.get("zone_id"),
            "recipient_id": r.get("id"),
            "phone": r.get("phone"),
            "role": r.get("role"),
            "language": lang,
            "body": body,
            "provider": "TWILIO" if _twilio_configured() else "LOG_ONLY",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **res,
        }
        await db.notifications.insert_one(dict(rec))
        rec.pop("_id", None)
        results.append(rec)
    return results
