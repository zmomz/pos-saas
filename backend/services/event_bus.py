"""Internal domain-event bus (ISSUE-218, M10 / §6.2).

The product already advertises a fixed set of outbound webhook events
(``product.created``, ``shift.closed``, … — :data:`services.production.WEBHOOK_EVENTS`),
but before this slice the only thing that ever consumed one was the webhook
dispatcher, wired directly into ``fire_event``. This module formalizes those
emissions into a real **publish/subscribe stream**: a source publishes a domain
event once, and any number of in-process subscribers react to it — outbound
webhook fan-out being just *one* such subscriber, alongside notification
materialization, and whatever future service wants to listen (read models,
audit projections, …) without the publisher knowing about it.

Subscribers are ``async def handler(ctx: EventContext)`` coroutines registered
for a specific event name or the ``"*"`` wildcard. They run in registration
order on :func:`publish`; one failing subscriber is logged and never blocks the
others (a flaky integration can't break the originating sale). The canonical
webhook fan-out subscriber is registered here at import and turns each event
into one durable ``webhook.deliver`` job per subscribed endpoint, routed through
:mod:`services.job_queue` — so webhook *delivery retries run on the queue*, not
inline in the request.
"""
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from services import job_queue

logger = logging.getLogger(__name__)

WILDCARD = "*"


@dataclass
class EventContext:
    """Everything a subscriber needs to react to one published event."""

    db: AsyncSession
    user_id: str
    event: str
    payload: Dict[str, Any]
    client_id: Optional[int] = None


EventHandler = Callable[[EventContext], Awaitable[Any]]

# event name (or WILDCARD) -> handlers, in registration order.
_SUBSCRIBERS: Dict[str, List[EventHandler]] = {}


def subscribe(event_type: str, handler: EventHandler) -> None:
    """Register ``handler`` for ``event_type`` (or ``"*"`` for every event)."""
    _SUBSCRIBERS.setdefault(event_type, []).append(handler)


def unsubscribe_all() -> None:
    """Drop every subscriber except the built-in fan-out (test isolation aid)."""
    _SUBSCRIBERS.clear()
    _register_builtins()


def _handlers_for(event: str) -> List[EventHandler]:
    return [*_SUBSCRIBERS.get(event, ()), *_SUBSCRIBERS.get(WILDCARD, ())]


async def publish(
    db: AsyncSession,
    user_id: str,
    event: str,
    payload: Dict[str, Any],
    *,
    client_id: Optional[int] = None,
) -> int:
    """Publish ``event`` to every subscriber; return the webhook fan-out count.

    The integer return is the number of outbound webhook endpoints the canonical
    fan-out subscriber scheduled — preserving the contract of the original
    ``fire_event`` (its callers and tests treat the count as "endpoints
    attempted"). Other subscribers (e.g. notification materialization) run for
    their side effects and contribute nothing to the count. Each subscriber is
    isolated: an exception is logged, never propagated.
    """
    ctx = EventContext(db=db, user_id=str(user_id), event=event, payload=payload, client_id=client_id)
    attempted = 0
    for handler in _handlers_for(event):
        try:
            result = await handler(ctx)
            if isinstance(result, int):
                attempted += result
        except Exception as exc:  # noqa: BLE001 - one bad subscriber can't break the rest
            logger.warning("Event subscriber for %s failed: %s", event, exc)
    return attempted


# ---------------------------------------------------------------------------
# Built-in subscriber: outbound webhook fan-out -> job queue
# ---------------------------------------------------------------------------
async def _webhook_fanout(ctx: EventContext) -> int:
    """Enqueue one ``webhook.deliver`` job per active endpoint subscribed to the event.

    Reads the user's ``webhooks`` rows (filtering on ``is_active`` and the
    endpoint's ``events`` subscription) and schedules a durable delivery job for
    each match. The HTTP POST + delivery-log write happens in the job (off the
    request path); this subscriber only fans out. Returns the number of endpoints
    scheduled, which becomes ``fire_event``'s "attempted" count.
    """
    from sqlalchemy import select

    from models.webhooks import Webhooks
    from services.production import _hook_subscribes

    try:
        rows = (
            await ctx.db.execute(select(Webhooks).where(Webhooks.user_id == ctx.user_id))
        ).scalars().all()
    except Exception as exc:  # pragma: no cover - lookup failure must not propagate
        logger.warning("Webhook lookup failed for event %s: %s", ctx.event, exc)
        return 0

    body = {"event": ctx.event, "data": ctx.payload}
    scheduled = 0
    for hook in rows:
        if hook.is_active is False:
            continue
        if not _hook_subscribes(hook.events, ctx.event):
            continue
        await job_queue.enqueue(
            "webhook.deliver",
            user_id=ctx.user_id,
            webhook_id=hook.id,
            url=hook.url,
            event=ctx.event,
            body=body,
            secret=hook.secret_key or "",
        )
        scheduled += 1
    return scheduled


def _register_builtins() -> None:
    subscribe(WILDCARD, _webhook_fanout)


_register_builtins()

# Importing the job module registers every queued job handler (webhook.deliver,
# zatca.reconcile, report.materialize, …) as a side effect, so the fan-out above
# always has a target by the time the first event is published.
from services import jobs  # noqa: E402,F401  (side-effect: job registration)
