"""Maintenance-mode middleware (M10 Admin, #225).

While the platform master has flipped maintenance mode on, ordinary tenant API
traffic is refused with ``503 Service Unavailable`` — but the master is never
locked out, so they can still reach the API (and the admin console) to turn it
back off.

The gate is deliberately narrow and *fails open*: it only touches ``/api/v1``
traffic, always lets an allowlist of paths through (auth so a master can log in,
the admin console so they can toggle it off, health probes), and treats any
error while checking the flag as "not in maintenance" so a settings hiccup can
never take the whole API down.
"""
import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from core.auth import AccessTokenError, decode_access_token
from core.database import db_manager
from dependencies.tenancy import resolve_owner_user_id
from services.platform_settings import get_maintenance_state

logger = logging.getLogger(__name__)

# Paths that must stay reachable even during maintenance: auth (so a master can
# log in), the admin console (so the master can toggle it off — still master-only
# at the endpoint), and health probes.
_ALLOW_PREFIXES = (
    "/api/v1/auth",
    "/api/v1/admin",
    "/api/v1/health",
)


class MaintenanceModeMiddleware(BaseHTTPMiddleware):
    """Refuse tenant traffic with 503 while platform maintenance mode is on."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        # Only gate real API traffic; never a preflight or an allowlisted path.
        if request.method == "OPTIONS" or not path.startswith("/api/v1") or path.startswith(_ALLOW_PREFIXES):
            return await call_next(request)

        try:
            async with db_manager.async_session_maker() as db:
                state = await get_maintenance_state(db)
                if not state["enabled"]:
                    return await call_next(request)
                # Maintenance is on — let the platform master through so they are
                # never locked out of their own platform.
                if await self._is_master(request, db):
                    return await call_next(request)
        except Exception:  # pragma: no cover - the gate must never fail closed
            logger.debug("maintenance gate errored; passing request through")
            return await call_next(request)

        return JSONResponse(
            status_code=503,
            content={"detail": state.get("message") or "Service temporarily unavailable for maintenance."},
            headers={"Retry-After": "3600"},
        )

    @staticmethod
    async def _is_master(request: Request, db) -> bool:
        """True iff the bearer token resolves to the unrestricted platform master."""
        auth = request.headers.get("authorization") or request.headers.get("Authorization")
        if not auth or not auth.lower().startswith("bearer "):
            return False
        token = auth.split(" ", 1)[1].strip()
        try:
            payload = decode_access_token(token)
        except AccessTokenError:
            return False
        if payload.get("type") == "refresh":
            return False
        sub = payload.get("sub")
        if not sub:
            return False
        # Master is the only scope with no owner (unrestricted) — reuse the one
        # tenancy resolver rather than re-deriving the role here.
        return await resolve_owner_user_id(db, sub) is None
