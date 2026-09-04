"""Persistence helpers for evidence uploaded to the private report-media bucket."""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.db import supabase_repo as repo


async def add_media(report_id: str, storage_path: str, media_type: str, mime_type: str, size_bytes: Optional[int] = None) -> Dict[str, Any]:
    client = await repo.client()
    row = {
        "report_id": report_id,
        "storage_path": storage_path,
        "media_type": media_type,
        "mime_type": mime_type,
        "size_bytes": size_bytes,
    }
    result = await client.table("report_media").insert(row).select("*").single().execute()
    return dict(result.data)


async def list_media(report_id: str) -> list[Dict[str, Any]]:
    client = await repo.client()
    result = await client.table("report_media").select("*").eq("report_id", report_id).order("created_at").execute()
    return [dict(x) for x in (result.data or [])]
