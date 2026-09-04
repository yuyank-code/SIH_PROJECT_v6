"""Authentication middleware for protected API routes.

Health/model metadata and explicitly public map endpoints stay public. All
other /api endpoints require a valid Supabase Auth bearer token and an active
profile. Authorization-sensitive writes additionally use route-level role
checks.
"""
from __future__ import annotations

import os
from typing import Callable

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse

PUBLIC_PATHS = {
    "/api/health", "/api/model/info", "/docs", "/openapi.json", "/redoc",
}
PUBLIC_PREFIXES = ("/api/public/",)


def install_auth_middleware(app) -> None:
    # NOTE: CORS is installed once in server.py *after* this call, so it becomes
    # the OUTERMOST middleware and wraps this auth layer. That ordering lets
    # browser preflight OPTIONS requests and 401/403 auth responses carry CORS
    # headers. Do NOT add a second CORSMiddleware here — two CORS layers emit
    # duplicate Access-Control-Allow-Origin headers, which browsers reject.

    @app.middleware("http")
    async def supabase_auth(request: Request, call_next: Callable):
        path = request.url.path
        if request.method == "OPTIONS" or path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES):
            return await call_next(request)
        if not path.startswith("/api/"):
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if not auth.lower().startswith("bearer "):
            return JSONResponse({"detail": "authentication_required"}, status_code=401)
        token = auth[7:].strip()
        if not token:
            return JSONResponse({"detail": "authentication_required"}, status_code=401)

        supabase_url = os.environ.get("SUPABASE_URL")
        if not supabase_url:
            return JSONResponse({"detail": "supabase_not_configured"}, status_code=500)

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{supabase_url.rstrip('/')}/auth/v1/user",
                    headers={"Authorization": f"Bearer {token}", "apikey": os.environ.get("SUPABASE_ANON_KEY", token)},
                )
            if response.status_code != 200:
                return JSONResponse({"detail": "invalid_or_expired_token"}, status_code=401)
            user = response.json()
            if not user.get("id"):
                return JSONResponse({"detail": "invalid_user"}, status_code=401)

            # Authorization is based on the server-side profile, never on
            # user-editable raw_user_meta_data or a client-selected role.
            from app.services.auth_service import get_profile
            profile = await get_profile(user["id"])
            if not profile or not profile.get("is_active"):
                return JSONResponse({"detail": "profile_inactive_or_missing"}, status_code=403)

            request.state.supabase_user = user
            request.state.profile = profile
        except httpx.HTTPError:
            return JSONResponse({"detail": "auth_service_unavailable"}, status_code=503)
        except Exception:
            return JSONResponse({"detail": "profile_lookup_failed"}, status_code=503)

        return await call_next(request)
