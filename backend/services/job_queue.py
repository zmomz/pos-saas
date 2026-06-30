"""Background job queue seam (ISSUE-218, M10 / §6.2).

Before this slice the only background worker was the hourly ``billing_scheduler``;
everything else (outbound webhook delivery, ZATCA reconcile, report
materialization, notifications, exports) rode FastAPI ``BackgroundTasks`` —
fire-and-forget work that is lost on a crash and has no durable retry. This
module introduces a single ``enqueue`` seam every such task funnels through, so
the *call sites never change* when the execution substrate does (the same
"swap-for-Redis-later behind one surface" pattern as
:mod:`services.token_revocation` and :mod:`services.kds_channel`).

Two interchangeable backends, chosen by ``JOB_QUEUE_BACKEND``:

* ``memory`` (default) — runs the job **inline** in the calling process with
  bounded exponential-backoff retry. No broker, so dev/CI and the single-node
  deployment need nothing extra, and behaviour is identical to the old
  background-task path (the job still completes before its caller returns).
* ``redis`` — enqueues onto a real Redis-backed `Arq <https://arq-docs.helpmanual.io>`_
  queue (``REDIS_URL``) drained by a separate ``worker.py`` process, so the work
  runs out-of-band and survives a crash, with Arq owning the durable retry.

Job functions are plain ``async def fn(**kwargs)`` coroutines registered under a
string name via :func:`register` / the :func:`job` decorator. :func:`run_job`
dispatches a name to its function and is what *both* backends ultimately call —
the memory backend directly, the Arq worker via ``worker.run_queued_job``.
"""
import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from core.config import settings

logger = logging.getLogger(__name__)

# name -> coroutine function. Populated at import time by the @job decorators in
# services/jobs.py (imported for its side effects from event_bus / worker).
_REGISTRY: Dict[str, Callable[..., Awaitable[Any]]] = {}

# Lazily-created Arq pool (redis backend only); cached for the process lifetime.
_arq_pool = None


def register(name: str, fn: Callable[..., Awaitable[Any]]) -> None:
    """Register ``fn`` under ``name`` (last registration wins; idempotent)."""
    _REGISTRY[name] = fn


def job(name: str) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Decorator form of :func:`register`."""

    def _decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        register(name, fn)
        return fn

    return _decorator


def registered_jobs() -> Dict[str, Callable[..., Awaitable[Any]]]:
    """The live registry (used by the Arq worker to expose every job)."""
    return dict(_REGISTRY)


def _backend() -> str:
    raw = str(getattr(settings, "job_queue_backend", "memory") or "memory").strip().lower()
    return raw if raw in ("memory", "redis") else "memory"


def _max_retries() -> int:
    try:
        return max(0, int(getattr(settings, "job_max_retries", 5)))
    except (TypeError, ValueError):
        return 5


async def run_job(name: str, **kwargs: Any) -> Any:
    """Look up and execute the job ``name`` once (no retry wrapper).

    Raises ``KeyError`` for an unknown job and propagates the job's own
    exceptions — the retry policy lives in the caller (memory backend) or in Arq
    (redis backend), so this stays a thin, testable dispatch.
    """
    fn = _REGISTRY.get(name)
    if fn is None:
        raise KeyError(f"No job registered under {name!r}")
    return await fn(**kwargs)


async def _run_inline_with_retries(name: str, kwargs: Dict[str, Any]) -> Any:
    """Memory backend: run a job inline, retrying transient failures.

    Bounded by ``job_max_retries`` with exponential backoff (0.1·2ⁿ s, capped),
    matching the durable retry the Redis worker gets from Arq. A job that keeps
    failing is logged and swallowed — a background job must never propagate into
    the request that scheduled it (best-effort, like the old BackgroundTasks path).
    """
    attempts = _max_retries() + 1
    last_exc: Optional[BaseException] = None
    for attempt in range(1, attempts + 1):
        try:
            return await run_job(name, **kwargs)
        except Exception as exc:  # noqa: BLE001 - bounded retry, then swallow
            last_exc = exc
            if attempt >= attempts:
                break
            backoff = min(0.1 * (2 ** (attempt - 1)), 5.0)
            logger.warning(
                "Job %s failed (attempt %d/%d): %s — retrying in %.1fs",
                name, attempt, attempts, exc, backoff,
            )
            await asyncio.sleep(backoff)
    logger.error("Job %s gave up after %d attempts: %s", name, attempts, last_exc)
    return None


async def _get_arq_pool():
    global _arq_pool
    if _arq_pool is not None:
        return _arq_pool
    from arq import create_pool  # lazy: only the redis backend needs arq
    from arq.connections import RedisSettings

    dsn = str(getattr(settings, "redis_url", "") or "").strip()
    if not dsn:
        raise RuntimeError("JOB_QUEUE_BACKEND=redis requires REDIS_URL to be set.")
    _arq_pool = await create_pool(RedisSettings.from_dsn(dsn))
    return _arq_pool


async def enqueue(name: str, **kwargs: Any) -> Optional[str]:
    """Schedule the job ``name`` to run, returning a job id when one exists.

    The single public seam. Under the memory backend the job runs inline (and
    this returns ``None``); under the redis backend it is pushed onto the Arq
    queue for the worker to drain (returning the Arq job id). Callers treat both
    the same: schedule and move on.
    """
    if name not in _REGISTRY:
        # Fail loud in dev — a typo'd job name would otherwise vanish silently.
        raise KeyError(f"No job registered under {name!r}")

    if _backend() == "redis":
        try:
            pool = await _get_arq_pool()
            arq_job = await pool.enqueue_job("run_queued_job", name, kwargs)
            return getattr(arq_job, "job_id", None)
        except Exception:  # pragma: no cover - broker down: degrade, don't drop
            # Prefer at-least-once over losing the work: if the broker is
            # unreachable we run the job inline. A failure *after* a successful
            # push (lost reply) could then run it twice — acceptable because the
            # only non-idempotent job, webhook.deliver, carries a unique
            # X-Webhook-Delivery id for receiver-side dedup, and every other job
            # is idempotent by construction.
            logger.exception("Redis enqueue of %s failed; running inline as fallback.", name)
            await _run_inline_with_retries(name, kwargs)
            return None

    await _run_inline_with_retries(name, kwargs)
    return None


async def close() -> None:
    """Close the Arq pool on shutdown (no-op under the memory backend)."""
    global _arq_pool
    if _arq_pool is not None:
        try:
            await _arq_pool.close()
        finally:
            _arq_pool = None
