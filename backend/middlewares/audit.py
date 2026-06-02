"""Audit-logging middleware.

Records an ``audit_logs`` row for:

* every **successful, mutating, authenticated** API request (POST/PUT/PATCH/
  DELETE on ``/api/v1`` returning 2xx) — capturing the acting user, the affected
  ``entity_type``/``entity_id`` (parsed from the path) and the submitted change
  set (the JSON request body, sensitive keys redacted = the "after" state); and
* **failed authentication/authorization** attempts (401/403) on protected
  endpoints, with action ``AUTH_FAILURE`` (Phase 3 audit completeness).

Auth endpoints are skipped so credentials are never persisted, and failures in
the middleware never affect the response.
"""
import json
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
# Request-body keys whose values must never be persisted to the audit trail.
_SENSITIVE_KEYS = {
    "password",
    "current_password",
    "new_password",
    "temp_password",
    "token",
    "refresh_token",
    "secret",
    "api_key",
    "card_number",
    "cvv",
}


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Write an audit row for authenticated mutations and failed-auth attempts."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Capture the JSON body up front and re-inject it so the downstream
        # handler (which receives a *different* Request instance) still reads it.
        # Only JSON bodies are touched — multipart/form uploads are left alone.
        body_bytes = await self._capture_json_body(request)
        if body_bytes is not None:

            async def _replay_receive():
                return {"type": "http.request", "body": body_bytes, "more_body": False}

            request._receive = _replay_receive  # type: ignore[attr-defined]

        response = await call_next(request)

        try:
            path = request.url.path
            if not path.startswith("/api/v1") or path.startswith(_SKIP_PREFIXES):
                return response

            user_id = self._user_id_from_request(request)
            client_host = request.client.host if request.client else None

            # Failed-auth / authorization attempt on a protected endpoint.
            if response.status_code in (401, 403):
                await write_audit_log(
                    user_id=user_id or "anonymous",
                    action=f"AUTH_FAILURE {request.method} {path}",
                    details=f"status={response.status_code}",
                    ip_address=client_host,
                )
                return response

            if request.method not in _MUTATING_METHODS:
                return response
            if not (200 <= response.status_code < 300):
                return response
            if not user_id:
                return response

            entity_type, entity_id = self._entity_from_path(path)
            changes = self._changes_from_bytes(body_bytes)
            await write_audit_log(
                user_id=user_id,
                action=f"{request.method} {path}",
                details=f"status={response.status_code}",
                ip_address=client_host,
                entity_type=entity_type,
                entity_id=entity_id,
                changes=changes,
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

    @staticmethod
    def _entity_from_path(path: str) -> tuple[str | None, str | None]:
        """Best-effort (entity_type, entity_id) from a REST-ish path.

        ``/api/v1/entities/products/5`` -> ("products", "5")
        ``/api/v1/pos/transactions/9/refund`` -> ("transactions", "9")
        """
        parts = [p for p in path.split("/") if p]
        entity_type = entity_id = None
        for i, part in enumerate(parts):
            if part == "entities" and i + 1 < len(parts):
                entity_type = parts[i + 1]
                if i + 2 < len(parts) and parts[i + 2].isdigit():
                    entity_id = parts[i + 2]
                return entity_type, entity_id
        # Fall back: a trailing /<int> identifies the entity id; the segment
        # before it names the collection.
        for i in range(len(parts) - 1, 0, -1):
            if parts[i].isdigit():
                return parts[i - 1], parts[i]
        return entity_type, entity_id

    @staticmethod
    async def _capture_json_body(request: Request) -> bytes | None:
        """Read the raw body for a JSON mutation so it can be re-injected.

        Returns the bytes for JSON-bodied POST/PUT/PATCH requests under the size
        cap, else ``None`` (leaving multipart/form uploads and GET/DELETE
        untouched so the stream is never disturbed for them).
        """
        if request.method not in ("POST", "PUT", "PATCH"):
            return None
        content_type = request.headers.get("content-type", "")
        if "application/json" not in content_type.lower():
            return None
        try:
            length = int(request.headers.get("content-length") or 0)
        except ValueError:
            length = 0
        if length > 64 * 1024:  # don't buffer very large payloads (e.g. CSV import)
            return None
        try:
            return await request.body()
        except Exception:  # pragma: no cover - defensive
            return None

    @classmethod
    def _changes_from_bytes(cls, body: bytes | None) -> str | None:
        """Return the JSON body with sensitive keys redacted ("after" state)."""
        if not body:
            return None
        try:
            data = json.loads(body)
        except (ValueError, TypeError):
            return None
        return json.dumps(cls._redact(data), ensure_ascii=False, default=str)

    @classmethod
    def _redact(cls, data):
        if isinstance(data, dict):
            return {
                k: ("***" if k.lower() in _SENSITIVE_KEYS else cls._redact(v))
                for k, v in data.items()
            }
        if isinstance(data, list):
            return [cls._redact(v) for v in data]
        return data
