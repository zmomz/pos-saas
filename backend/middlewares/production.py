"""
Production middleware for the multi-tenant POS system.
Provides rate limiting, performance monitoring, and structured logging.
CORS configuration lives in ``core/cors.py`` (the single source of truth).
"""

import json
import logging
import os
import time
import uuid
from typing import List, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from services.production import performance_monitor, rate_limiter

logger = logging.getLogger(__name__)


def _env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean feature flag from the environment at call time.

    Read live (not via the cached settings singleton) so operators — and the
    test-suite — can toggle middleware behaviour without rebuilding the app.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# =============================================================================
# Structured JSON Logging
# =============================================================================
class StructuredLogFormatter(logging.Formatter):
    """JSON structured log formatter with correlation IDs."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add correlation ID if present
        if hasattr(record, "correlation_id"):
            log_data["correlation_id"] = record.correlation_id

        # Add extra fields
        if hasattr(record, "extra_data"):
            log_data["data"] = record.extra_data

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False, default=str)


def setup_structured_logging(log_level: str = "INFO"):
    """Configure structured JSON logging for the application."""
    formatter = StructuredLogFormatter()
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    for existing_handler in root_logger.handlers[:]:
        root_logger.removeHandler(existing_handler)

    root_logger.addHandler(handler)


# =============================================================================
# Rate Limiting Middleware
# =============================================================================
class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces per-user rate limiting using token bucket.
    Extracts user identity from Authorization header or falls back to IP.
    """

    def __init__(self, app, exclude_paths: Optional[List[str]] = None):
        super().__init__(app)
        self.exclude_paths = exclude_paths or [
            "/docs",
            "/openapi.json",
            "/redoc",
            "/database/health",
            "/api/v1/production/health/detailed",
        ]

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Disabled by default; enable per-deployment with RATE_LIMIT_ENABLED=true.
        if not _env_flag("RATE_LIMIT_ENABLED", False):
            return await call_next(request)

        # Skip excluded paths
        if any(request.url.path.startswith(p) for p in self.exclude_paths):
            return await call_next(request)

        # Identify user by auth token or IP
        user_identifier = self._get_user_identifier(request)

        # Check rate limit
        if not rate_limiter.is_allowed(user_identifier):
            logger.warning(
                "Rate limit exceeded for user: %s on path: %s",
                user_identifier[:16],
                request.url.path,
            )
            return Response(
                content=json.dumps({
                    "detail": "Rate limit exceeded. Please try again later.",
                    "retry_after_seconds": 1,
                }),
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": "1"},
            )

        response = await call_next(request)

        # Add rate limit headers
        remaining = rate_limiter.get_remaining(user_identifier)
        response.headers["X-RateLimit-Remaining"] = str(int(remaining))
        response.headers["X-RateLimit-Limit"] = str(rate_limiter.max_tokens)

        return response

    @staticmethod
    def _get_user_identifier(request: Request) -> str:
        """Extract user identifier from request."""
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            # Use a hash of the token as identifier (don't store raw tokens)
            import hashlib
            token_hash = hashlib.sha256(auth_header[7:].encode()).hexdigest()
            return f"token:{token_hash[:32]}"

        # Fall back to client IP
        client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}"


# =============================================================================
# Performance Monitoring Middleware
# =============================================================================
class PerformanceMiddleware(BaseHTTPMiddleware):
    """Middleware that tracks response times and logs slow requests."""

    SLOW_REQUEST_THRESHOLD_MS = 1000  # Log requests slower than 1 second

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Generate correlation ID
        correlation_id = str(uuid.uuid4())[:8]
        request.state.correlation_id = correlation_id

        start_time = time.time()

        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.time() - start_time) * 1000
            performance_monitor.record_request(
                endpoint=request.url.path,
                response_time_ms=elapsed_ms,
                is_error=True,
            )
            raise

        elapsed_ms = (time.time() - start_time) * 1000
        is_error = response.status_code >= 400

        # Record metric
        performance_monitor.record_request(
            endpoint=request.url.path,
            response_time_ms=elapsed_ms,
            is_error=is_error,
        )

        # Log slow requests
        if elapsed_ms > self.SLOW_REQUEST_THRESHOLD_MS:
            logger.warning(
                "Slow request: %s %s took %.2fms (correlation: %s)",
                request.method,
                request.url.path,
                elapsed_ms,
                correlation_id,
            )

        # Add performance headers
        response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.2f}"
        response.headers["X-Correlation-ID"] = correlation_id

        return response


# =============================================================================
# API-Usage Metering Middleware
# =============================================================================
class ApiUsageMeteringMiddleware(BaseHTTPMiddleware):
    """Persist one ``api_usage`` row per authenticated API request (Phase 3).

    Powers ``GET /api/v1/production/api-usage/stats`` with real data (request
    counts + average response time per endpoint). Disabled by default so dev/CI
    add no write overhead; enable with ``API_METERING_ENABLED=true``. Writes are
    best-effort in their own session and never affect the response.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not _env_flag("API_METERING_ENABLED", False):
            return await call_next(request)

        start = time.time()
        response = await call_next(request)
        elapsed_ms = int((time.time() - start) * 1000)

        try:
            path = request.url.path
            if not path.startswith("/api/v1"):
                return response
            user_id = self._user_id(request)
            if not user_id:
                return response
            await self._record(
                user_id=user_id,
                endpoint=path,
                method=request.method,
                status_code=response.status_code,
                response_time_ms=elapsed_ms,
            )
        except Exception as exc:  # pragma: no cover - metering must not break requests
            logger.debug("API metering skipped a request: %s", exc)

        return response

    @staticmethod
    def _user_id(request: Request) -> Optional[str]:
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return None
        from core.auth import AccessTokenError, decode_access_token

        try:
            payload = decode_access_token(auth.split(" ", 1)[1].strip())
        except AccessTokenError:
            return None
        if payload.get("type") == "refresh":
            return None
        return payload.get("sub")

    @staticmethod
    async def _record(user_id, endpoint, method, status_code, response_time_ms) -> None:
        from datetime import datetime, timezone

        from core.database import db_manager
        from dependencies.tenancy import resolve_owner_user_id
        from models.api_usage import Api_usage

        if not db_manager.async_session_maker:
            return
        async with db_manager.async_session_maker() as db:
            # Tag the row with the owning merchant so a merchant's usage query
            # aggregates all staff activity, not only the owner's own requests
            # (finding H4).
            owner_user_id = await resolve_owner_user_id(db, user_id)
            db.add(
                Api_usage(
                    user_id=str(user_id),
                    owner_user_id=owner_user_id,
                    endpoint=endpoint[:255],
                    method=method,
                    status_code=status_code,
                    response_time_ms=response_time_ms,
                    request_date=datetime.now(timezone.utc).date().isoformat(),
                )
            )
            await db.commit()


# =============================================================================
# Request Validation Middleware
# =============================================================================
class RequestValidationMiddleware(BaseHTTPMiddleware):
    """Middleware for basic request validation and sanitization."""

    DEFAULT_MAX_BODY_MB = 10  # 10MB max body size

    def _max_body_size(self) -> int:
        """Body-size cap in bytes; override with MAX_BODY_SIZE_MB at runtime."""
        try:
            mb = int(os.environ.get("MAX_BODY_SIZE_MB", self.DEFAULT_MAX_BODY_MB))
        except (TypeError, ValueError):
            mb = self.DEFAULT_MAX_BODY_MB
        return max(1, mb) * 1024 * 1024

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Check content length
        max_bytes = self._max_body_size()
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                declared = int(content_length)
            except ValueError:
                declared = 0
            if declared > max_bytes:
                return Response(
                    content=json.dumps(
                        {"detail": f"Request body too large. Maximum size is {max_bytes // (1024 * 1024)}MB."}
                    ),
                    status_code=413,
                    media_type="application/json",
                )

        # Validate content type for POST/PUT/PATCH
        if request.method in ("POST", "PUT", "PATCH"):
            content_type = request.headers.get("content-type", "")
            if content_type and "application/json" not in content_type and "multipart/form-data" not in content_type:
                # Allow requests without content-type (some clients don't set it)
                pass

        return await call_next(request)