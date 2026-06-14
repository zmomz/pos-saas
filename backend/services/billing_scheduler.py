"""Always-on billing scheduler (ISSUE-052).

The dunning/retry sweep used to run only on an agent's manual HTTP trigger
(``POST /tenant/agent/billing/run-dunning``). This module adds a config-gated
background task that runs the *platform-wide* sweep
(:func:`services.dunning.run_global_dunning`) on a fixed interval, so overdue
subscriptions advance through dunning automatically with no human in the loop.

Gating (so dev/CI never spawns a background charger):
  * ``BILLING_SCHEDULER_ENABLED`` (default off) turns the loop on.
  * ``BILLING_SCHEDULER_INTERVAL_SECONDS`` (default 3600) sets the cadence.

:func:`start_billing_scheduler` is invoked from the FastAPI lifespan and returns
the :class:`asyncio.Task` (or ``None`` when disabled); :func:`stop_billing_scheduler`
cancels it on shutdown. :func:`run_billing_sweep_once` is the single tick — it
opens a fresh session and runs one sweep, and is what tests invoke directly to
exercise the scheduled path without spinning the loop.
"""
import asyncio
import logging
from typing import Optional

from core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 3600

# The system actor recorded on audit rows for an unattended (scheduler) sweep,
# distinguishing it from an agent-triggered run.
SYSTEM_ACTOR = "system:billing-scheduler"

_task: Optional[asyncio.Task] = None


def _enabled() -> bool:
    val = getattr(settings, "billing_scheduler_enabled", False)
    if isinstance(val, str):
        return val.strip().lower() in ("1", "true", "yes", "on")
    return bool(val)


def _interval_seconds() -> int:
    raw = getattr(settings, "billing_scheduler_interval_seconds", DEFAULT_INTERVAL_SECONDS)
    try:
        return max(60, int(raw or DEFAULT_INTERVAL_SECONDS))
    except (TypeError, ValueError):
        return DEFAULT_INTERVAL_SECONDS


async def run_billing_sweep_once() -> dict:
    """Run one platform-wide dunning/retry sweep in a fresh session and commit.

    The background loop calls this each tick; tests call it directly to exercise
    the unattended path. Returns the sweep summary.
    """
    from core.database import db_manager
    from services.dunning import run_global_dunning

    async with db_manager.async_session_maker() as db:
        return await run_global_dunning(db, actor_user_id=SYSTEM_ACTOR)


async def _scheduler_loop(interval: int) -> None:
    logger.info("Billing scheduler started (interval=%ss).", interval)
    try:
        while True:
            await asyncio.sleep(interval)
            try:
                summary = await run_billing_sweep_once()
                logger.info("Billing sweep complete: %s", summary)
            except Exception:  # pragma: no cover - a tick failure must not kill the loop
                logger.exception("Billing sweep tick failed; retrying next interval.")
    except asyncio.CancelledError:  # pragma: no cover - shutdown path
        logger.info("Billing scheduler stopped.")
        raise


def start_billing_scheduler() -> Optional[asyncio.Task]:
    """Start the background sweep loop when ``BILLING_SCHEDULER_ENABLED``.

    No-op (returns ``None``) when disabled, so dev/CI never spawns an unattended
    charger. Idempotent: if a live task already exists it is returned as-is.
    """
    global _task
    if not _enabled():
        logger.info("Billing scheduler disabled (BILLING_SCHEDULER_ENABLED unset).")
        return None
    if _task is not None and not _task.done():
        return _task
    _task = asyncio.create_task(_scheduler_loop(_interval_seconds()))
    return _task


async def stop_billing_scheduler() -> None:
    """Cancel the background sweep loop if running (lifespan shutdown)."""
    global _task
    if _task is not None and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
