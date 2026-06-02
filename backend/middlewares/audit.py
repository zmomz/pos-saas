"""Audit-logging middleware.

Automatically records an ``audit_logs`` row for every **successful, mutating,
authenticated** API request (POST/PUT/PATCH/DELETE on ``/api/v1`` that returns a
2xx). The acting user is resolved from the bearer token. Auth endpoints are
skipped so we never persist anything alongside credentials, and failures never
affect the response.
"""
import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from core.auth import AccessTokenError, decode_access_token
from services.audit import write_audit_log

logger = logging.getLogger(__name__)

_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Never audit auth flows (token material in body) or read-only/utility paths.
_SKIP_PREFIXES = (
    "/api/v1/auth",
    "/api/v1/integrations/email",
)


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Write an audit row for authenticated, successful mutations."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        try:
            if request.method not in _MUTATING_METHODS:
                return response
            path = request.url.path
            if not path.startswith("/api/v1") or path.startswith(_SKIP_PREFIXES):
                return response
            if not (200 <= response.status_code < 300):
                return response

            user_id = self._user_id_from_request(request)
            if not user_id:
                return response

            client_host = request.client.host if request.client else None
            await write_audit_log(
                user_id=user_id,
                action=f"{request.method} {path}",
                details=f"status={response.status_code}",
                ip_address=client_host,
            )
        except Exception as exc:  # pragma: no cover - auditing must not break the response
            logger.debug("Audit middleware skipped a request: %s", exc)

        return response

    @staticmethod
    def _user_id_from_request(request: Request) -> str | None:
        auth = request.headers.get("authorization") or request.headers.get("Authorization")
        if not auth or not auth.lower().startswith("bearer "):
            return None
        token = auth.split(" ", 1)[1].strip()
        try:
            payload = decode_access_token(token)
        except AccessTokenError:
            return None
        if payload.get("type") == "refresh":
            return None
        return payload.get("sub")
