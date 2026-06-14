import logging
import os
from typing import Any

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # Application
    app_name: str = "FastAPI Modular Template"
    debug: bool = False
    version: str = "1.0.0"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    database_url: str = "sqlite:///./app.db"

    # JWT / local authentication
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24h access token
    refresh_token_expire_minutes: int = 10080  # 7 days refresh token

    # CORS: comma-separated list of allowed origins (e.g.
    # "https://app.example.com,https://admin.example.com"). When empty, behavior
    # depends on ENVIRONMENT (see core/cors.py): dev allows any origin, prod
    # falls back to localhost only.
    allowed_origins: str = ""

    # Master/admin bootstrap account (seeded on startup if it does not exist)
    admin_email: str = ""
    admin_password: str = ""
    admin_name: str = "Administrator"

    # Allow open self-registration via POST /api/v1/auth/register.
    # Disable in production once the master account and provisioning are set up.
    allow_registration: bool = True

    # Login brute-force protection (ISSUE-043). Failed logins are counted per
    # (identifier, IP); once login_max_attempts failures accumulate within
    # login_attempt_window_minutes the pair is locked out for
    # login_lockout_minutes. A successful login clears the counter.
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15
    login_attempt_window_minutes: int = 15

    # ZATCA Phase-2 (Fatoora) e-invoicing.
    #   zatca_environment: sandbox | simulation | production (selects the
    #     Fatoora gateway + CSR template). Network calls are skipped (503)
    #     unless a base URL resolves.
    #   zatca_api_base_url: explicit gateway override (e.g. a local mock).
    #   zatca_encryption_key: AES-256 key material for secrets at rest;
    #     falls back to jwt_secret_key in dev. MUST be set in production.
    #   zatca_retention_years: statutory archival period for signed invoices.
    zatca_environment: str = "sandbox"
    zatca_api_base_url: str = ""
    zatca_encryption_key: str = ""
    zatca_retention_years: int = 6
    # ISSUE-016 (C2 gating): live Fatoora submission is OFF by default. Every sale
    # is still signed, stamped, hash-chained and archived locally, but documents
    # fail closed to "pending" instead of being POSTed to the gateway until an
    # operator has validated the signed UBL against a Fatoora sandbox and flips
    # this on. Prevents silently emitting invoices a live gateway would reject.
    zatca_live_submission_enabled: bool = False

    # Always-on billing scheduler (ISSUE-052). When enabled, a background task
    # runs the platform-wide dunning/retry sweep every
    # billing_scheduler_interval_seconds. Off by default so dev/CI never spawns an
    # unattended subscription charger.
    billing_scheduler_enabled: bool = False
    billing_scheduler_interval_seconds: int = 3600

    # Object storage (OSS) — ISSUE-030. When both are set, StorageService talks
    # to the external object-storage gateway. When either is absent the service
    # degrades to a clear 503 (never an unhandled 500), and storage-backed
    # features (e.g. CSV-export archival) fall back to inline content.
    oss_service_url: str = ""
    oss_api_key: str = ""

    # Error tracking (Phase E). When sentry_dsn is set AND the optional
    # `sentry-sdk` package is installed, errors are reported to Sentry; otherwise
    # observability is a no-op. See core/observability.py.
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.0

    @property
    def backend_url(self) -> str:
        """Generate backend URL from host and port."""
        display_host = "127.0.0.1" if self.host == "0.0.0.0" else self.host
        return os.environ.get("PYTHON_BACKEND_URL", f"http://{display_host}:{self.port}")

    class Config:
        case_sensitive = False
        extra = "ignore"

    def __getattr__(self, name: str) -> Any:
        """
        Dynamically read attributes from environment variables.
        For example: settings.opapi_key reads from OPAPI_KEY environment variable.

        Args:
            name: Attribute name (e.g., 'opapi_key')

        Returns:
            Value from environment variable

        Raises:
            AttributeError: If attribute doesn't exist and not found in environment variables
        """
        # Convert attribute name to environment variable name (snake_case -> UPPER_CASE)
        env_var_name = name.upper()

        # Check if environment variable exists
        if env_var_name in os.environ:
            value = os.environ[env_var_name]
            # Cache the value in instance dict to avoid repeated lookups
            self.__dict__[name] = value
            logger.debug(f"Read dynamic attribute {name} from environment variable {env_var_name}")
            return value

        # If not found, raise AttributeError to maintain normal Python behavior
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")


# Global settings instance
settings = Settings()
