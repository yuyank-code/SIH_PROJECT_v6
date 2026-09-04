"""Route-level authorization using the server-side Supabase profile."""
from __future__ import annotations

from typing import Callable

from fastapi import HTTPException, Request


ROLE_ALIASES = {
    "ADMIN": {"ADMIN"},
    "AUTHORITY": {"ADMIN", "AUTHORITY"},
    "FIELD_OFFICER": {"ADMIN", "AUTHORITY", "FIELD_OFFICER"},
    "CITIZEN": {"ADMIN", "AUTHORITY", "FIELD_OFFICER", "CITIZEN"},
}


def require_roles(*roles: str) -> Callable:
    allowed = set()
    for role in roles:
        allowed.update(ROLE_ALIASES.get(role, {role}))

    async def dependency(request: Request):
        profile = getattr(request.state, "profile", None)
        if not profile or not profile.get("is_active"):
            raise HTTPException(status_code=403, detail="active_profile_required")
        if profile.get("role") not in allowed:
            raise HTTPException(status_code=403, detail="insufficient_role")
        return profile

    return dependency
