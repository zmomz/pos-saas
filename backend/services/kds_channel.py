"""Pluggable pub/sub broker for the Kitchen-Display real-time channel (F-057).

The KDS needs fired/bumped/recalled cards to appear on the kitchen board in
**near-real-time (≤1s, SRS §5.1)**. The transport chosen for this seam is
**Server-Sent Events (SSE)**, not WebSocket: the kitchen board is a one-way
server→client feed (the cook's bump/recall actions go over ordinary POST
endpoints, not back up the stream), SSE rides plain HTTP with auto-reconnect
built into the browser ``EventSource``, and it needs **no extra dependency** —
the one simple option that hits the target (see the F-057 PR notes).

Fan-out has two layers behind a single ``subscribe`` / ``unsubscribe`` /
``publish`` surface (M6, #212):

* **In-process (default).** Each subscriber (an open KDS stream) holds an
  ``asyncio.Queue`` keyed by the owner's ``user_id``; a fire/bump/recall delivers
  the already-serialized event to every queue for that owner within the
  event-loop tick. This is a single-process broker — an event published in one
  worker never reaches subscribers in another, so it caps the restaurant tier at
  one worker (ARC-09).

* **Redis pub/sub (horizontal scale).** When ``REDIS_URL`` / ``KDS_REDIS_URL`` is
  set, ``publish`` writes the event to a shared Redis channel instead, and every
  worker runs a background listener that re-injects incoming messages into its
  own local queues. Events therefore fan out across all workers, lifting the
  single-worker constraint — the KDS routes and the frontend never see the
  difference (master plan §6.2 / M6).

The boot guard (``assert_single_worker_safe``, called from ``main.lifespan``)
only fires for the in-process backend: once the Redis backend is active a
multi-worker restaurant deploy is safe, so the assertion no longer blocks it.
"""
import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)


# --- Backend selection -----------------------------------------------------
# A Redis URL in the environment switches the channel to the shared pub/sub
# backend; absent it, the in-process backend is used (single worker). REDIS_URL
# is the conventional form; KDS_REDIS_URL lets an operator point the KDS channel
# at a different instance from any future cache/queue use.
_REDIS_URL_ENV_VARS = ("KDS_REDIS_URL", "REDIS_URL")
# One shared channel for all owners; each message carries its own user_id so a
# worker can fan it out to the right local subscribers.
_REDIS_CHANNEL = "kds:events"


def _configured_redis_url() -> Optional[str]:
    """Return the first configured Redis URL, or None for the in-process path."""
    for name in _REDIS_URL_ENV_VARS:
        raw = os.environ.get(name, "").strip()
        if raw:
            return raw
    return None


# --- Single-worker safety guard (ARC-09) -----------------------------------
# The in-process backend fans events out only within its own process. Under more
# than one uvicorn/gunicorn worker, an event published in one worker never reaches
# the SSE subscribers attached to another, so kitchen-board updates are silently
# dropped. The Redis backend removes that limitation; the guard below therefore
# only refuses to boot when the *in-process* backend would run under >1 worker.
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


def assert_single_worker_safe(
    worker_count: Optional[int] = None, *, broker: Optional["KdsChannel"] = None
) -> None:
    """Fail loud when the in-process KDS broker would run under >1 worker.

    Called at application startup (main.lifespan) *after* the channel has been
    configured. When a shared (Redis) backend is active the channel already fans
    events across workers, so this is a no-op — the assertion no longer blocks a
    multi-worker restaurant deploy (#212). Otherwise ``worker_count`` is resolved
    from the environment when not given: a single-worker configuration (the
    default) is a no-op; a multi-worker one raises ``RuntimeError`` with an
    actionable message unless the operator has explicitly opted in via
    ``KDS_ALLOW_MULTI_WORKER``.
    """
    active = broker if broker is not None else kds_broker
    if active is not None and active.is_multi_worker_safe:
        return
    if os.environ.get(_ALLOW_MULTI_WORKER_ENV, "").strip().lower() in _TRUTHY:
        return
    count = worker_count if worker_count is not None else _configured_worker_count()
    if count > 1:
        raise RuntimeError(
            f"KDS real-time broker is in-process (services/kds_channel.py) and "
            f"cannot fan events across {count} workers — kitchen-board updates "
            f"would be silently dropped. Configure a shared backend by setting "
            f"REDIS_URL (or KDS_REDIS_URL), run a single worker (unset/lower "
            f"WEB_CONCURRENCY/UVICORN_WORKERS/GUNICORN_WORKERS), or set "
            f"{_ALLOW_MULTI_WORKER_ENV}=1 if a shared broker already fronts the "
            f"process (ARC-09, #212)."
        )


class _LocalRegistry:
    """Per-owner registry of the open SSE streams in *this* process.

    Both backends share it: the in-process backend delivers straight into it,
    and the Redis backend delivers into it from its listener once a message
    arrives off the shared channel. The queues only ever live in the process
    that owns the SSE connection.
    """

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

    def deliver(self, user_id: str, event: Dict[str, Any]) -> None:
        """Fan an event out to every open stream for one owner (non-blocking).

        A slow/backed-up subscriber (queue full) is skipped rather than blocking
        the publisher — the board will reconcile on its next snapshot/reconnect.
        """
        for queue in list(self._subscribers.get(user_id, set())):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:  # pragma: no cover - slow consumer backpressure
                logger.warning("KDS subscriber queue full for user %s; dropping event", user_id)


class InProcessKdsBackend:
    """Single-process fan-out (the default). Publish delivers locally at once."""

    is_multi_worker_safe = False

    def __init__(self) -> None:
        self._local = _LocalRegistry()

    def subscribe(self, user_id: str) -> asyncio.Queue:
        return self._local.subscribe(user_id)

    def unsubscribe(self, user_id: str, queue: asyncio.Queue) -> None:
        self._local.unsubscribe(user_id, queue)

    async def publish(self, user_id: str, event: Dict[str, Any]) -> None:
        self._local.deliver(user_id, event)

    async def start(self) -> None:  # pragma: no cover - trivial
        pass

    async def stop(self) -> None:  # pragma: no cover - trivial
        pass


class RedisKdsBackend:
    """Shared pub/sub fan-out over Redis — events cross worker boundaries (#212).

    ``publish`` writes ``{"user_id", "event"}`` to ``_REDIS_CHANNEL``; a
    background listener subscribed to that channel delivers each incoming message
    into this process's local queues. Every worker runs both halves, so an event
    fired in any worker reaches the SSE streams attached to all of them.
    """

    is_multi_worker_safe = True

    def __init__(self, url: str, channel: str = _REDIS_CHANNEL) -> None:
        self._url = url
        self._channel = channel
        self._local = _LocalRegistry()
        self._redis: Any = None
        self._pubsub: Any = None
        self._listener_task: Optional[asyncio.Task] = None

    def subscribe(self, user_id: str) -> asyncio.Queue:
        return self._local.subscribe(user_id)

    def unsubscribe(self, user_id: str, queue: asyncio.Queue) -> None:
        self._local.unsubscribe(user_id, queue)

    async def start(self) -> None:
        """Connect, subscribe to the shared channel, and start the listener."""
        try:
            import redis.asyncio as redis  # lazy: only the Redis path needs it
        except ImportError as exc:  # pragma: no cover - depends on deployment
            raise RuntimeError(
                "REDIS_URL is set for the KDS channel but the 'redis' package is "
                "not installed — add redis>=5.0 (see requirements.txt) or unset "
                "REDIS_URL/KDS_REDIS_URL to use the in-process backend (#212)."
            ) from exc

        self._redis = redis.from_url(self._url, decode_responses=True)
        # Verify connectivity up front so a bad URL fails boot loudly rather than
        # silently dropping every kitchen event.
        await self._redis.ping()
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(self._channel)
        self._listener_task = asyncio.create_task(self._listen())
        logger.info("KDS real-time channel: Redis pub/sub backend on '%s'.", self._channel)

    async def _listen(self) -> None:
        """Fan messages off the shared channel into this process's local queues."""
        try:
            async for message in self._pubsub.listen():
                if message is None or message.get("type") != "message":
                    continue
                try:
                    envelope = json.loads(message["data"])
                    user_id = envelope["user_id"]
                    event = envelope["event"]
                except (KeyError, ValueError, TypeError):
                    logger.warning("KDS Redis listener dropped a malformed message")
                    continue
                self._local.deliver(user_id, event)
        except asyncio.CancelledError:  # pragma: no cover - shutdown path
            raise
        except Exception:  # pragma: no cover - defensive; keep the worker alive
            logger.exception("KDS Redis listener stopped unexpectedly")

    async def publish(self, user_id: str, event: Dict[str, Any]) -> None:
        if self._redis is None:  # pragma: no cover - publish before start
            # Not started (e.g. a unit test instantiated us directly): fall back
            # to local delivery so a single process still sees its own events.
            self._local.deliver(user_id, event)
            return
        await self._redis.publish(
            self._channel, json.dumps({"user_id": user_id, "event": event})
        )

    async def stop(self) -> None:
        """Tear down the listener and Redis connections on shutdown."""
        if self._listener_task is not None:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except (asyncio.CancelledError, Exception):  # pragma: no cover
                pass
            self._listener_task = None
        if self._pubsub is not None:
            try:
                await self._pubsub.aclose()
            except Exception:  # pragma: no cover - best-effort cleanup
                pass
            self._pubsub = None
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:  # pragma: no cover - best-effort cleanup
                pass
            self._redis = None


class KdsChannel:
    """Process-wide facade over the active backend (in-process or Redis).

    Callers import the ``kds_broker`` singleton and use ``subscribe`` /
    ``unsubscribe`` / ``publish`` without knowing which backend is live;
    ``configure`` (run once at startup) picks the backend from the environment.
    """

    def __init__(self) -> None:
        self._backend: Any = InProcessKdsBackend()

    @property
    def is_multi_worker_safe(self) -> bool:
        return bool(getattr(self._backend, "is_multi_worker_safe", False))

    def subscribe(self, user_id: str) -> asyncio.Queue:
        return self._backend.subscribe(user_id)

    def unsubscribe(self, user_id: str, queue: asyncio.Queue) -> None:
        self._backend.unsubscribe(user_id, queue)

    async def publish(self, user_id: str, event: Dict[str, Any]) -> None:
        await self._backend.publish(user_id, event)

    async def configure(self, *, redis_url: Optional[str] = None) -> None:
        """Select and start the backend. Redis when a URL is set, else in-process.

        Idempotent in spirit: the in-process default is left in place when no
        Redis URL is configured, so a startup with no Redis never disturbs any
        already-attached subscribers.
        """
        url = redis_url if redis_url is not None else _configured_redis_url()
        if not url:
            logger.info("KDS real-time channel: in-process backend (single worker).")
            return
        backend = RedisKdsBackend(url)
        await backend.start()
        self._backend = backend

    async def shutdown(self) -> None:
        await self._backend.stop()


# Process-wide singleton (one per uvicorn worker). Starts on the in-process
# backend; main.lifespan calls ``configure`` to switch to Redis when configured.
kds_broker = KdsChannel()
