"""FCM push delivery for Supabase-registered device tokens."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable

import httpx
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleRequest

SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]


def _credentials():
    raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    if not raw: raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON is not configured")
    return service_account.Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)

def _access_token() -> tuple[str, str]:
    credentials = _credentials(); credentials.refresh(GoogleRequest()); project_id = credentials.project_id
    if not project_id: raise RuntimeError("firebase_project_id_missing")
    return credentials.token, project_id

async def send_to_token(token: str, title: str, body: str, data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    access_token, project_id = _access_token()
    payload={"message":{"token":token,"notification":{"title":title,"body":body},"data":{str(k):str(v) for k,v in (data or {}).items()}}}
    async with httpx.AsyncClient(timeout=15) as client:
        response=await client.post(f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send",headers={"Authorization":f"Bearer {access_token}","Content-Type":"application/json"},json=payload)
    if response.status_code >= 400: raise RuntimeError(f"fcm_error_{response.status_code}: {response.text[:500]}")
    return response.json()

async def send_to_tokens(tokens: Iterable[str], title: str, body: str, data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    sent=0; failed_tokens=[]; errors=[]
    for token in tokens:
        try:
            await send_to_token(token,title,body,data); sent += 1
        except Exception as exc:
            failed_tokens.append(token); errors.append(str(exc))
    return {"sent":sent,"failed":len(failed_tokens),"failed_tokens":failed_tokens,"errors":errors}
