"""In-process pub/sub broker for the Kitchen-Display real-time channel (F-057).

The KDS needs fired/bumped/recalled cards to appear on the kitchen board in
**near-real-time (≤1s, SRS §5.1)**. The transport chosen for this seam is
**Server-Sent Events (SSE)**, not WebSocket: the kitchen board is a one-way
server→client feed (the cook's bump/recall actions go over ordinary POST
endpoints, not back up the stream), SSE rides plain HTTP with auto-reconnect
built into the browser ``EventSource``, and it needs **no extra dependency** —
the one simple option that hits the target (see the F-057 PR notes).

Fan-out is process-local: each subscriber (an open KDS stream) holds an
``asyncio.Queue`` keyed by the owner's ``user_id``; a fire/bump/recall publishes
the already-serialized event to every queue for that owner, so the board updates
within the event-loop tick (well under the 1s target) without polling. This is a
single-process broker — a multi-worker deployment would swap this for Redis
pub/sub behind the same ``publish`` / ``subscribe`` surface; the KDS routes and
the frontend never see the difference. Until that shared broker exists the
single-worker invariant is *enforced*, not just assumed: ``assert_single_worker_safe``
(called from ``main.lifespan`` at startup) aborts the boot under a multi-worker
configuration so events can never be silently dropped (ARC-09).
"""
import asyncio
import logging
import os
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)


# --- Single-worker safety guard (ARC-09) -----------------------------------
# The broker below fans events out only within its own process. Under more than
# one uvicorn/gunicorn worker, an event published in one worker never reaches the
# SSE subscribers attached to another, so kitchen-board updates are silently
# dropped. Until a shared broker (e.g. Redis pub/sub) backs publish/subscribe,
# KDS requires a single worker; the startup guard below enforces that loudly.
#
# uvicorn reads WEB_CONCURRENCY as its default worker count; UVICORN_WORKERS /
# GUNICORN_WORKERS are the explicit forms. Any of them > 1 means multi-worker.
_WORKER_COUNT_ENV_VARS = ("WEB_CONCURRENCY", "UVICORN_WORKERS", "GUNICORN_WORKERS")
# Escape hatch for an operator who has put a shared broker (or owner-sticky load
# balancing) in front of the in-process one and accepts the responsibility.
_ALLOW_MULTI_WORKER_ENV = "KDS_ALLOW_MULTI_WORKER"
_TRUTHY = {"1", "true", "yes", "on"}


def _configured_worker_count() -> int:
    """Resolve the configured worker count from the environment (default 1)."""
    count = 1
    for name in _WORKER_COUNT_ENV_VARS:
        raw = os.environ.get(name, "").strip()
        if not raw:
            continue
        try:
            count = max(count, int(raw))
        except ValueError:
            # A non-numeric value is not a multi-worker signal; ignore it.
            continue
    return count


def assert_single_worker_safe(worker_count: Optional[int] = None) -> None:
    """Fail loud when the in-process KDS broker would run under >1 worker.

    Called at application startup (main.lifespan). ``worker_count`` is resolved
    from the environment when not given. A single-worker configuration (the
    default, and the only one run.ps1/CI use) is a no-op; a multi-worker one
    raises ``RuntimeError`` with an actionable message unless the operator has
    explicitly opted in via ``KDS_ALLOW_MULTI_WORKER``.
    """
    if os.environ.get(_ALLOW_MULTI_WORKER_ENV, "").strip().lower() in _TRUTHY:
        return
    count = worker_count if worker_count is not None else _configured_worker_count()
    if count > 1:
        raise RuntimeError(
            f"KDS real-time broker is in-process (services/kds_channel.py) and "
            f"cannot fan events across {count} workers — kitchen-board updates "
            f"would be silently dropped. Run a single worker (unset/lower "
            f"WEB_CONCURRENCY/UVICORN_WORKERS/GUNICORN_WORKERS), or set "
            f"{_ALLOW_MULTI_WORKER_ENV}=1 once a shared broker (e.g. Redis "
            f"pub/sub) backs publish/subscribe (ARC-09, #166)."
        )


class KdsBroker:
    """Per-owner fan-out of KDS events to the subscribed kitchen streams."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}

    def subscribe(self, user_id: str) -> asyncio.Queue:
        """Register an open stream and return its event queue."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.setdefault(user_id, set()).add(queue)
        logger.debug("KDS stream subscribed for user %s", user_id)
        return queue

    def unsubscribe(self, user_id: str, queue: asyncio.Queue) -> None:
        """Drop a closed stream's queue (and prune the owner's empty bucket)."""
        subs = self._subscribers.get(user_id)
        if not subs:
            return
        subs.discard(queue)
        if not subs:
            self._subscribers.pop(user_id, None)
        logger.debug("KDS stream unsubscribed for user %s", user_id)

    def publish(self, user_id: str, event: Dict[str, Any]) -> None:
        """Fan an event out to every open stream for one owner (non-blocking).

        A slow/backed-up subscriber (queue full) is skipped rather than blocking
        the publisher — the board will reconcile on its next snapshot/reconnect.
        """
        for queue in list(self._subscribers.get(user_id, set())):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:  # pragma: no cover - slow consumer backpressure
                logger.warning("KDS subscriber queue full for user %s; dropping event", user_id)


# Process-wide singleton (one event loop per uvicorn worker).
kds_broker = KdsBroker()
