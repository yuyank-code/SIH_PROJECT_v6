"""Server-side Supabase Auth helpers.

The frontend should use the Supabase client for sign-in/session refresh. The
backend only needs the authenticated user's JWT context and profile/role.
Service-role credentials must never be exposed to the frontend.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from supabase import AsyncClient, acreate_client

_admin: Optional[AsyncClient] = None


async def admin_client() -> AsyncClient:
    global _admin
    if _admin is not None:
        return _admin
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("Supabase server credentials are not configured")
    _admin = await acreate_client(url, key)
    return _admin


async def get_profile(user_id: str) -> Optional[Dict[str, Any]]:
    c = await admin_client()
    result = await c.table("profiles").select("*").eq("id", user_id).maybe_single().execute()
    return dict(result.data) if result.data else None


async def ensure_profile(user_id: str, full_name: Optional[str] = None, phone: Optional[str] = None) -> Dict[str, Any]:
    c = await admin_client()
    existing = await get_profile(user_id)
    if existing:
        return existing
    result = await c.table("profiles").insert({"id": user_id, "full_name": full_name, "phone": phone, "role": "CITIZEN", "is_active": True}).select("*").single().execute()
    return dict(result.data)
