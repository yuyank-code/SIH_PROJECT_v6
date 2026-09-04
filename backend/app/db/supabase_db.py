"""Supabase database adapter used during the Mongo -> Supabase migration.

The adapter deliberately returns the legacy zone shape expected by the risk
service, so the ML/risk code does not need to change while persistence moves.
Server credentials are read only from environment variables and are never
exposed to the frontend.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from supabase import AsyncClient, acreate_client

_client: Optional[AsyncClient] = None


async def init_supabase() -> AsyncClient:
    global _client
    if _client is not None:
        return _client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY are required")

    _client = await acreate_client(url, key)
    return _client


async def close_supabase() -> None:
    global _client
    if _client is None:
        return
    # supabase-py owns an HTTP client internally; closing the auth session is
    # the supported cleanup operation for server-side clients.
    try:
        await _client.auth.sign_out()
    finally:
        _client = None


def _zone_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a PostGIS row into the shape used by risk_service.py."""
    centroid = row.get("centroid") or {}
    boundary = row.get("boundary")
    terrain = {
        "elevation_m": row.get("elevation_m"),
        "slope_deg": row.get("slope_deg"),
        "aspect_sin": row.get("aspect_sin"),
        "aspect_cos": row.get("aspect_cos"),
        "curvature_1_m": row.get("curvature_1_m"),
    }
    terrain = {k: v for k, v in terrain.items() if v is not None}
    return {
        "id": row.get("id"),
        "zone_id": row.get("zone_id"),
        "name": row.get("name"),
        "district": row.get("district"),
        "state": row.get("state"),
        "centroid": centroid,
        "geometry": boundary,
        "population": row.get("population"),
        "terrain": terrain,
        "terrain_source": row.get("terrain_source"),
        "road_blocked": row.get("road_blocked", False),
        "isolated_villages": row.get("isolated_villages", 0),
        "recent_field_report": row.get("recent_field_report", False),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


async def list_zones(state: Optional[str] = None) -> List[Dict[str, Any]]:
    client = await init_supabase()
    query = client.table("zones").select("*").order("zone_id")
    if state:
        query = query.eq("state", state)
    response = await query.execute()
    return [_zone_from_row(row) for row in (response.data or [])]


async def get_zone(zone_id: str) -> Optional[Dict[str, Any]]:
    client = await init_supabase()
    response = (
        await client.table("zones")
        .select("*")
        .eq("zone_id", zone_id)
        .maybe_single()
        .execute()
    )
    if not response.data:
        return None
    return _zone_from_row(response.data)


async def count_zones() -> int:
    client = await init_supabase()
    response = await client.table("zones").select("id", count="exact").execute()
    return int(response.count or 0)
