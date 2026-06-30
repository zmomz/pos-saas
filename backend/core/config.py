import logging
import os
import secrets as _secrets
from typing import Any

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

# Source-visible default JWT secret. Booting prod with this (or anything weak)
# lets anyone forge HS256 tokens and impersonate the master admin (SEC-01).
DEFAULT_JWT_SECRET = "change-me-in-production"
# Minimum entropy we accept for a signing key in production.
MIN_JWT_SECRET_LENGTH = 32


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

    # ISSUE-185: refresh-cookie SameSite policy. The default (False) keeps the
    # FE-01 same-origin posture — SameSite=Lax, which rides same-origin XHR and
    # resists CSRF. Set REFRESH_COOKIE_CROSS_SITE=true ONLY when the SPA and API
    # are served on different sites: the cookie then becomes SameSite=None;Secure
    # (the sole combination a browser sends on cross-site credentialed XHR), so
    # /auth/refresh keeps working across the origin split. Cross-site mode is
    # meaningless without credentialed CORS pinned to explicit origins, so
    # validate_secrets() refuses a prod boot that enables it while ALLOWED_ORIGINS
    # is empty (a wildcard origin can't carry credentials).
    refresh_cookie_cross_site: bool = False

    # Master/admin bootstrap account (seeded on startup if it does not exist)
    admin_email: str = ""
    admin_password: str = ""
    admin_name: str = "Administrator"

    # Allow open self-registration via POST /api/v1/auth/register.
    # Defaults OFF (SEC-10): this is a wholesale-quota platform where accounts are
    # provisioned by master/agents, not self-minted. Set ALLOW_REGISTRATION=true to
    # opt in for self-serve deployments. Provisioning paths are unaffected.
    allow_registration: bool = False

    # Login brute-force protection (ISSUE-043). Failed logins are counted per
    # (identifier, IP); once login_max_attempts failures accumulate within
    # login_attempt_window_minutes the pair is locked out for
    # login_lockout_minutes. A successful login clears the counter.
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15
    login_attempt_window_minutes: int = 15
    # SEC-15: two additional cross-cutting counters keyed independently of the
    # (identifier, IP) pair so a distributed run can't slip under the per-pair
    # threshold. login_account_max_attempts locks an identifier once that many
    # failures accumulate across *all* source IPs (defeats distributed spray
    # against one account). login_ip_max_attempts locks a source IP once that
    # many failures accumulate across *all* identifiers (defeats one host
    # spraying many accounts); its threshold is higher to limit NAT false
    # positives. Both share login_attempt_window_minutes / login_lockout_minutes.
    login_account_max_attempts: int = 5
    login_ip_max_attempts: int = 50

    # Password-complexity policy (ISSUE-084). Enforced at every set-password
    # entry point — signup, reset, change-password, and staff-login
    # provisioning. Defaults require a mixed-case alphanumeric of at least 8
    # characters; symbols are optional. Tune per deployment via env vars
    # (e.g. PASSWORD_MIN_LENGTH=12, PASSWORD_REQUIRE_SYMBOL=true).
    password_min_length: int = 8
    password_require_uppercase: bool = True
    password_require_lowercase: bool = True
    password_require_digit: bool = True
    password_require_symbol: bool = False

    # ZATCA Phase-2 (Fatoora) e-invoicing.
    #   zatca_environment: sandbox | simulation | production (selects the
    #     Fatoora gateway + CSR template). Network calls are skipped (503)
    #     unless a base URL resolves.
    #   zatca_api_base_url: explicit gateway override (e.g. a local mock).
    #   secrets_encryption_key: the dedicated AES-256 key material for ALL
    #     secrets at rest (SEC-05). Preferred over zatca_encryption_key; both
    #     fall back to jwt_secret_key in dev. MUST be set in production —
    #     validate_secrets() refuses prod boot on the JWT fallback.
    #   zatca_encryption_key: legacy key, kept so already-encrypted ZATCA
    #     material stays readable. Falls back to jwt_secret_key in dev.
    #   zatca_retention_years: statutory archival period for signed invoices.
    zatca_environment: str = "sandbox"
    zatca_api_base_url: str = ""
    secrets_encryption_key: str = ""
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

    # Job queue + internal event bus (ISSUE-218, M10 / §6.2). Background work
    # (webhook-delivery retries, ZATCA reconcile, report materialization,
    # notifications, exports) is funnelled through one ``services.job_queue``
    # seam. The default backend "memory" runs each queued job inline in the
    # originating process — no broker, so dev/CI need nothing extra and existing
    # behaviour is preserved. Set JOB_QUEUE_BACKEND=redis (with REDIS_URL) to
    # enqueue onto a real Redis-backed Arq queue drained by a separate worker
    # process (see ``worker.py``), so the work survives a crash and runs
    # out-of-band of the request that triggered it.
    job_queue_backend: str = "memory"
    redis_url: str = ""
    # Per-job durable retry budget for the queue (webhook delivery, reconcile,
    # …). The memory backend retries inline with exponential backoff; the Redis
    # backend maps this onto Arq's ``max_tries``.
    job_max_retries: int = 5
    # Arq cron cadence: how often the worker re-enqueues the platform-wide ZATCA
    # reconcile + report-materialization sweeps. Only meaningful under the redis
    # backend; 0 disables the periodic enqueue.
    queue_sweep_interval_seconds: int = 900

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


def _is_dev() -> bool:
    """Match the project-wide dev detection (see core/cors.py)."""
    return os.getenv("ENVIRONMENT", "prod").lower() == "dev"


def dedicated_secrets_key() -> str:
    """The dedicated at-rest encryption key, independent of the JWT secret.

    Resolves ``SECRETS_ENCRYPTION_KEY`` first, then the legacy
    ``ZATCA_ENCRYPTION_KEY`` (kept so already-encrypted ZATCA material stays
    readable). Returns an empty string when neither is configured — i.e. when
    :func:`core.crypto._aes_key` would fall back to the JWT secret.
    """
    return (
        (getattr(settings, "secrets_encryption_key", "") or "")
        or (getattr(settings, "zatca_encryption_key", "") or "")
    ).strip()


def validate_secrets() -> None:
    """Fail fast on insecure secret material before serving traffic.

    Validates, in order, the JWT signing key (SEC-01) and the at-rest
    secrets-encryption key (SEC-05). Both abort prod boot when misconfigured
    while keeping dev runs frictionless.

    Called from the application lifespan before ``initialize_database``.
    """
    _validate_jwt_secret()
    _validate_secrets_encryption_key()
    _validate_cookie_policy()


def _validate_jwt_secret() -> None:
    """Fail fast on an insecure JWT signing key before serving traffic.

    HS256 with a known/weak key enables token forgery and full admin
    impersonation, so in production we abort boot when the JWT secret is unset,
    equals the source-visible default, or carries too little entropy. In dev we
    keep local runs frictionless by swapping in a generated ephemeral key
    instead of refusing to start.
    """
    secret = (getattr(settings, "jwt_secret_key", "") or "").strip()
    if not secret:
        reason = "is unset"
    elif secret == DEFAULT_JWT_SECRET:
        reason = "equals the source-visible default"
    elif len(secret) < MIN_JWT_SECRET_LENGTH:
        reason = f"is shorter than {MIN_JWT_SECRET_LENGTH} characters"
    else:
        return  # Strong, explicitly configured key — nothing to do.

    if _is_dev():
        settings.jwt_secret_key = _secrets.token_urlsafe(48)
        logger.warning(
            "JWT secret %s; generated an ephemeral dev key. Set JWT_SECRET_KEY "
            "to keep sessions valid across restarts.",
            reason,
        )
        return

    raise RuntimeError(
        f"Refusing to start: the JWT secret {reason}. Set a strong, unique "
        f"JWT_SECRET_KEY (>= {MIN_JWT_SECRET_LENGTH} characters) in the environment."
    )


def _validate_cookie_policy() -> None:
    """Guard the ISSUE-185 cross-site refresh-cookie invariant.

    Cross-site mode emits ``SameSite=None`` so the refresh cookie rides
    cross-site credentialed XHR, but the browser only attaches it when CORS
    answers that XHR with credentials — and credentialed CORS is impossible
    against a wildcard origin. So enabling cross-site mode without an explicit
    ``ALLOWED_ORIGINS`` list silently re-breaks refresh exactly as the same-site
    Lax cookie did. In production we refuse to boot on that contradiction; in dev
    we only warn so local cross-site experiments stay frictionless.
    """
    if not getattr(settings, "refresh_cookie_cross_site", False):
        return  # Same-origin default imposes no extra requirement.

    if (getattr(settings, "allowed_origins", "") or "").strip():
        return  # Explicit credentialed origins configured — invariant holds.

    if _is_dev():
        logger.warning(
            "REFRESH_COOKIE_CROSS_SITE is on but ALLOWED_ORIGINS is empty; "
            "cross-site refresh needs credentialed CORS pinned to explicit "
            "origins. Set ALLOWED_ORIGINS before production."
        )
        return

    raise RuntimeError(
        "Refusing to start: REFRESH_COOKIE_CROSS_SITE is enabled but "
        "ALLOWED_ORIGINS is empty. A SameSite=None refresh cookie is only sent "
        "on cross-site XHR that CORS answers with credentials, which requires "
        "explicit origins (a wildcard cannot carry credentials). Set "
        "ALLOWED_ORIGINS, or disable REFRESH_COOKIE_CROSS_SITE for a same-origin "
        "deployment."
    )


def _validate_secrets_encryption_key() -> None:
    """Require a dedicated at-rest encryption key in production (SEC-05).

    Stored secrets (payment-gateway keys, saved-card tokens, ZATCA credentials)
    are AES-256-GCM encrypted under a key that, absent a dedicated value, falls
    back to the JWT signing secret. Sharing the signing key with the
    data-encryption key means one leak compromises both, so prod must set
    ``SECRETS_ENCRYPTION_KEY`` (or the legacy ``ZATCA_ENCRYPTION_KEY``). Dev
    keeps the JWT fallback so local runs need no extra configuration.
    """
    if dedicated_secrets_key():
        return  # A dedicated key is configured — nothing to do.

    if _is_dev():
        logger.warning(
            "No dedicated secrets-encryption key; falling back to the JWT secret "
            "for at-rest encryption. Set SECRETS_ENCRYPTION_KEY before production."
        )
        return

    raise RuntimeError(
        "Refusing to start: stored secrets would be encrypted under the JWT "
        "signing key. Set a dedicated SECRETS_ENCRYPTION_KEY (or the legacy "
        "ZATCA_ENCRYPTION_KEY) in the environment."
    )
