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
the frontend never see the difference.
"""
import asyncio
import logging
from typing import Any, Dict, Set

logger = logging.getLogger(__name__)


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
