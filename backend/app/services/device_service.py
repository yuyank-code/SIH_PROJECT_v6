"""Device registration helpers for FCM/mobile push tokens."""
from __future__ import annotations

from typing import Any, Dict

from app.db import supabase_repo as repo


async def register_device(fcm_token: str, platform: str) -> Dict[str, Any]:
    client = await repo.client()
    result = await client.rpc("register_device", {"p_fcm_token": fcm_token, "p_platform": platform}).execute()
    if not result.data:
        raise ValueError("device_registration_failed")
    return dict(result.data)


async def deactivate_device(device_id: str) -> bool:
    client = await repo.client()
    result = await client.table("user_devices").update({"is_active": False}).eq("id", device_id).execute()
    return bool(result.data)
