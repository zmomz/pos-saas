"""Arq worker entry point for the Redis-backed job queue (ISSUE-218, M10).

Run only under ``JOB_QUEUE_BACKEND=redis`` (with ``REDIS_URL`` set), as a
separate process from the API::

    cd backend && arq worker.WorkerSettings

It drains the queue that :func:`services.job_queue.enqueue` pushes onto: a
single Arq task, :func:`run_queued_job`, dispatches each ``(name, kwargs)`` to
its registered coroutine via :func:`services.job_queue.run_job`. Arq owns the
durable retry — a job that raises is re-tried up to ``max_tries`` with backoff,
which is how webhook-delivery retries / reconcile survive a crash here.

Two periodic crons re-enqueue the platform-wide sweeps (ZATCA reconcile + alert
materialization) so they run on the queue rather than as ad-hoc manual triggers.
Under the default ``memory`` backend none of this runs — the API process
executes jobs inline — so importing this module must stay dependency-free until
its functions are actually called by Arq.
"""
import logging
from typing import Any, Dict

from core.config import settings
from services import event_bus  # noqa: F401  (side-effect: registers every job)
from services.job_queue import run_job

logger = logging.getLogger(__name__)


async def run_queued_job(ctx: Dict[str, Any], name: str, kwargs: Dict[str, Any]) -> Any:
    """Arq task: execute one enqueued job by name. Raises propagate to Arq's retry."""
    logger.info("Running queued job %s (try %s)", name, ctx.get("job_try"))
    return await run_job(name, **(kwargs or {}))


async def cron_reconcile_zatca(ctx: Dict[str, Any]) -> Any:
    """Periodic platform-wide ZATCA reconcile sweep (all clients)."""
    return await run_job("zatca.reconcile")


async def cron_materialize_reports(ctx: Dict[str, Any]) -> Any:
    """Periodic platform-wide alert-feed materialization sweep (all clients)."""
    return await run_job("report.materialize")


def _redis_settings():
    from arq.connections import RedisSettings

    dsn = str(getattr(settings, "redis_url", "") or "").strip()
    return RedisSettings.from_dsn(dsn) if dsn else RedisSettings()


def _sweep_minutes(interval_seconds: int) -> set:
    """The minute-of-hour grid the sweeps fire on for a requested interval.

    Arq cron is calendar-based (a set of minutes), so an arbitrary second
    interval can't be honored exactly. We snap the requested step to the nearest
    divisor of 60 (capped at 30 ⇒ at least twice an hour) so the cadence is
    *evenly spaced* — never the irregular gaps a non-divisor ``range`` step would
    produce, and never collapsing to once-an-hour for large values.
    """
    step_min = max(1, interval_seconds // 60)
    divisors = (1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30)
    step = min(divisors, key=lambda d: (abs(d - step_min), d)) if step_min < 30 else 30
    return set(range(0, 60, step))


def _cron_jobs():
    from arq import cron

    interval = int(getattr(settings, "queue_sweep_interval_seconds", 900) or 0)
    if interval <= 0:
        return []
    minutes = _sweep_minutes(interval)
    return [
        cron(cron_reconcile_zatca, minute=minutes, run_at_startup=False),
        cron(cron_materialize_reports, minute=minutes, run_at_startup=False),
    ]


class WorkerSettings:
    """Arq worker configuration. Referenced as ``worker.WorkerSettings``."""

    functions = [run_queued_job]
    cron_jobs = _cron_jobs()
    max_tries = int(getattr(settings, "job_max_retries", 5)) + 1
    redis_settings = _redis_settings()
