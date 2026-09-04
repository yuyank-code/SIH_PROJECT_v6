"""FastAPI authentication against Supabase Auth access tokens."""
from __future__ import annotations

import os
from typing import Any, Dict

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)


async def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> Dict[str, Any]:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="authentication_required")
    url = os.environ.get("SUPABASE_URL")
    if not url:
        raise HTTPException(status_code=500, detail="supabase_not_configured")
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{url.rstrip('/')}/auth/v1/user", headers={"Authorization": f"Bearer {credentials.credentials}", "apikey": os.environ.get("SUPABASE_ANON_KEY", credentials.credentials)})
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="invalid_or_expired_token")
    user = response.json()
    if not user.get("id"):
        raise HTTPException(status_code=401, detail="invalid_user")
    return user


async def require_authority(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    from app.services.auth_service import get_profile
    profile = await get_profile(user["id"])
    if not profile or not profile.get("is_active") or profile.get("role") not in {"ADMIN", "AUTHORITY", "FIELD_OFFICER"}:
        raise HTTPException(status_code=403, detail="authority_role_required")
    return {**user, "profile": profile}
