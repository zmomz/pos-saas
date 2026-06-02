"""
Production middleware for the multi-tenant POS system.
Provides rate limiting, performance monitoring, structured logging,
and CORS lockdown helpers.
"""

import json
import logging
import time
import uuid
from typing import List, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from services.production import performance_monitor, rate_limiter

logger = logging.getLogger(__name__)


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
# CORS Lockdown Helper
# =============================================================================
def get_cors_config(environment: str = "production") -> dict:
    """
    Get CORS configuration based on environment.
    In production, restrict to known origins.
    In development, allow broader access.
    """
    if environment == "development":
        return {
            "allow_origins": ["*"],
            "allow_credentials": True,
            "allow_methods": ["*"],
            "allow_headers": ["*"],
        }
    elif environment == "staging":
        return {
            "allow_origins": [
                "https://staging.yourdomain.com",
                "https://staging-admin.yourdomain.com",
            ],
            "allow_credentials": True,
            "allow_methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
            "allow_headers": ["Authorization", "Content-Type", "X-Requested-With"],
        }
    else:
        # Production - most restrictive
        return {
            "allow_origins": [
                "https://yourdomain.com",
                "https://admin.yourdomain.com",
                "https://pos.yourdomain.com",
            ],
            "allow_credentials": True,
            "allow_methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
            "allow_headers": ["Authorization", "Content-Type", "X-Requested-With"],
            "max_age": 3600,
        }


# =============================================================================
# Request Validation Middleware
# =============================================================================
class RequestValidationMiddleware(BaseHTTPMiddleware):
    """Middleware for basic request validation and sanitization."""

    MAX_BODY_SIZE = 10 * 1024 * 1024  # 10MB max body size

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Check content length
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.MAX_BODY_SIZE:
            return Response(
                content=json.dumps({"detail": "Request body too large. Maximum size is 10MB."}),
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