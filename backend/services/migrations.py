"""Run Alembic migrations programmatically on boot (Phase 3 — OPS-01).

The schema is owned by the versioned Alembic chain, **not** by runtime
``create_all`` + ad-hoc ``ALTER`` (OPS-01: *"schema via versioned migrations, not
runtime ALTER"*). So in production this helper runs ``alembic upgrade head``
during startup *before* any request is served, and the caller then **skips**
``create_all`` (see ``services/database.py::initialize_database``).

``RUN_MIGRATIONS_ON_BOOT`` decides the policy, but its default is now
environment-aware (``migrations_on_boot_enabled``): **on in production**, off in
``ENVIRONMENT=dev`` / CI so the fast ``create_all`` path and the test fixture stay
unaffected. An explicit ``RUN_MIGRATIONS_ON_BOOT`` always wins. If migrations are
enabled but fail (e.g. a legacy DB created by an older ``create_all`` with no
``alembic_version`` stamp), startup falls back to ``create_all`` so the app still
boots — the failure is logged for the operator.

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


def migrations_on_boot_enabled() -> bool:
    """Whether Alembic migrations own the schema at boot (so ``create_all`` must not run).

    Decision (pure, env-driven — the single source of truth shared by
    ``run_migrations_on_boot`` and ``initialize_database``):

    * an explicit ``RUN_MIGRATIONS_ON_BOOT`` (truthy/falsy) always wins;
    * otherwise default **on in production**, **off in ``ENVIRONMENT=dev``** (and
      CI, which sets ``ENVIRONMENT=dev``) so dev/CI keep using ``create_all``.

    The ``ENVIRONMENT`` default mirrors ``core/cors.py`` (unset → ``"prod"``).
    """
    raw = os.environ.get("RUN_MIGRATIONS_ON_BOOT")
    if raw is not None:
        return raw.strip().lower() in ("1", "true", "yes", "on")
    return os.environ.get("ENVIRONMENT", "prod").strip().lower() != "dev"


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


async def run_migrations_on_boot() -> bool:
    """Run migrations when enabled; report whether they now own the schema.

    Executed inside the FastAPI lifespan. Returns ``True`` only when
    ``alembic upgrade head`` succeeded — the caller then **skips** ``create_all``
    so the schema comes purely from the versioned migration chain (OPS-01).

    Returns ``False`` when migrations are disabled (dev/CI) **or** when they were
    enabled but failed: the failure is logged but does not crash startup, and the
    caller falls back to ``create_all`` so the app still boots with a usable schema
    (e.g. a legacy DB created by an older ``create_all`` with no ``alembic_version``).
    """
    if not migrations_on_boot_enabled():
        logger.info("Migrations-on-boot disabled (dev/CI or RUN_MIGRATIONS_ON_BOOT off); create_all will bootstrap the schema.")
        return False
    try:
        import asyncio

        await asyncio.to_thread(run_upgrade_head)
        logger.info("Alembic upgrade head completed on boot; create_all will be skipped.")
        return True
    except Exception as exc:  # pragma: no cover - exercised only in prod-like envs
        logger.error("Alembic upgrade head failed on boot: %s — falling back to create_all.", exc, exc_info=True)
        return False
