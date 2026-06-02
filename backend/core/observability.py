"""Error tracking / observability bootstrap (Phase E).

Config-gated Sentry initialisation. This is a **no-op** unless both a
``SENTRY_DSN`` is configured *and* the optional ``sentry_sdk`` package is
installed — so the app runs identically in dev/CI where neither is present, and
starts reporting to Sentry the moment an operator sets the DSN in production.

Wired from ``main.py`` at import time. Returns ``True`` only when Sentry was
actually initialised, which keeps the behaviour trivially testable.
"""
import logging
import os

logger = logging.getLogger(__name__)


def _resolve_dsn() -> str:
    # settings.__getattr__ resolves SENTRY_DSN, but read the env directly to
    # avoid importing settings before logging is configured.
    return (os.environ.get("SENTRY_DSN") or "").strip()


def init_sentry() -> bool:
    """Initialise Sentry if configured. Returns whether it was enabled."""
    dsn = _resolve_dsn()
    if not dsn:
        logger.info("Sentry disabled (no SENTRY_DSN configured).")
        return False

    try:
        import sentry_sdk  # type: ignore
    except ImportError:
        logger.warning(
            "SENTRY_DSN is set but the 'sentry-sdk' package is not installed; "
            "error tracking is disabled. Run `pip install sentry-sdk` to enable."
        )
        return False

    environment = os.environ.get("ENVIRONMENT", "prod")
    try:
        traces_rate = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0"))
    except ValueError:
        traces_rate = 0.0

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        traces_sample_rate=traces_rate,
        send_default_pii=False,
    )
    logger.info("Sentry error tracking initialised (environment=%s).", environment)
    return True
