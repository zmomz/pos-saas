"""Run Alembic migrations programmatically on boot (Phase 3).

By default the app bootstraps its schema with ``Base.metadata.create_all`` (fast,
dependency-light, and what the test fixture relies on). In production you want a
real migration history instead, so set ``RUN_MIGRATIONS_ON_BOOT=true`` and this
helper runs ``alembic upgrade head`` during startup *before* any request is
served. It is intentionally **off by default** so dev/CI keep using ``create_all``
and the test suite is unaffected.

The Alembic config is loaded from ``backend/alembic.ini``; ``alembic/env.py``
resolves the database URL from application settings, so no URL needs to be passed.
"""
import logging
import os

logger = logging.getLogger(__name__)


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _alembic_ini_path() -> str:
    # backend/services/migrations.py -> backend/alembic.ini
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "alembic.ini")


def run_upgrade_head() -> None:
    """Run ``alembic upgrade head`` synchronously. Raises on failure."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(_alembic_ini_path())
    command.upgrade(cfg, "head")


async def run_migrations_on_boot() -> None:
    """Run migrations if ``RUN_MIGRATIONS_ON_BOOT`` is enabled (best-effort).

    Executed inside the FastAPI lifespan. A migration failure is logged but does
    not crash startup (the subsequent ``create_all`` still bootstraps a usable
    schema) — operators monitoring logs will see the error.
    """
    if not _env_flag("RUN_MIGRATIONS_ON_BOOT", False):
        logger.info("Migrations-on-boot disabled (RUN_MIGRATIONS_ON_BOOT not set).")
        return
    try:
        import asyncio

        await asyncio.to_thread(run_upgrade_head)
        logger.info("Alembic upgrade head completed on boot.")
    except Exception as exc:  # pragma: no cover - exercised only in prod-like envs
        logger.error("Alembic upgrade head failed on boot: %s", exc, exc_info=True)
