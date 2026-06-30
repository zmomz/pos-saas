"""Registered background jobs (ISSUE-218, M10 / §6.2).

Every unit of background work the platform runs is defined here as an
``async def fn(**kwargs)`` coroutine registered with :mod:`services.job_queue`
under a stable name. The queue's backend decides *where* they run (inline under
``memory``, on an Arq worker under ``redis``); this module only says *what* each
one does. Jobs are self-contained — they open their own DB session (the request
that scheduled them is long gone, exactly like ``billing_scheduler``) and take
only JSON-serializable kwargs so the redis backend can round-trip them.

Jobs registered:

* ``webhook.deliver`` — POST one signed outbound webhook with delivery logging;
  raises on a terminal failure so the queue retries it (webhook-retry rail).
* ``zatca.reconcile`` — resubmit a client's stuck ZATCA documents (or sweep all
  clients) — the reconcile rail.
* ``report.materialize`` — (re)materialize a client's alert feed (or sweep all
  clients) — the report-materialization rail.
* ``notification.dispatch`` — deliver one preference-honoring notification.
* ``export.generate`` — render a client's product catalog to CSV (exports rail).
"""
import logging
from typing import Any, Dict, Optional

from services.job_queue import job

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Webhook delivery (retry rail)
# ---------------------------------------------------------------------------
@job("webhook.deliver")
async def deliver_webhook(
    *,
    user_id: str,
    webhook_id: Optional[int],
    url: str,
    event: str,
    body: Dict[str, Any],
    secret: str = "",
) -> Dict[str, Any]:
    """Deliver one signed webhook and persist the outcome.

    Wraps :meth:`services.production.WebhookDispatcher.dispatch` (HMAC signing +
    its bounded transient-failure retry) and records the result to
    ``webhook_deliveries`` in a fresh session. This is the unit of work the queue
    schedules: under the memory backend it runs inline in the originating
    process; under the redis backend it runs on the Arq worker (and Arq re-runs
    it on worker crash). Exactly **one** delivery row is written per job run —
    matching the ISSUE-029 "one row per attempted endpoint" invariant — so the
    retry budget is owned by ``dispatch`` and the queue, not duplicated by
    re-recording. Never raises: a non-delivered outcome is logged as a failed
    delivery, exactly as the old inline ``fire_event`` recorded it.
    """
    from core.database import db_manager
    from services.production import WebhookDispatcher, record_delivery

    result = await WebhookDispatcher.dispatch(url, event, body, secret or "")

    await db_manager.ensure_initialized()
    async with db_manager.async_session_maker() as db:
        await record_delivery(db, str(user_id), webhook_id, url, event, result)
    return result


# ---------------------------------------------------------------------------
# ZATCA reconcile (reconcile rail)
# ---------------------------------------------------------------------------
@job("zatca.reconcile")
async def reconcile_zatca(*, client_id: Optional[int] = None) -> Dict[str, Any]:
    """Resubmit stuck (pending/failed) ZATCA documents to Fatoora.

    With ``client_id`` it reconciles one merchant; without it, it sweeps every
    client (the periodic worker cron path). Runs in its own session and commits.
    Mirrors the manual ``POST /zatca/documents/report-pending`` endpoint, now on
    the queue.
    """
    from sqlalchemy import select

    from core.database import db_manager
    from services import zatca_sale

    await db_manager.ensure_initialized()
    summary: Dict[str, Any] = {}
    async with db_manager.async_session_maker() as db:
        if client_id is not None:
            summary = await zatca_sale.report_pending_documents(db, int(client_id))
        else:
            from models.clients import Clients

            ids = (await db.execute(select(Clients.id))).scalars().all()
            totals = {"clients": 0, "processed": 0, "cleared": 0, "reported": 0, "pending": 0, "failed": 0}
            for cid in ids:
                one = await zatca_sale.report_pending_documents(db, int(cid))
                totals["clients"] += 1
                for k in ("processed", "cleared", "reported", "pending", "failed"):
                    totals[k] += int(one.get(k, 0))
            summary = totals
        await db.commit()
    logger.info("ZATCA reconcile job complete: %s", summary)
    return summary


# ---------------------------------------------------------------------------
# Report / alert-feed materialization (materialization rail)
# ---------------------------------------------------------------------------
@job("report.materialize")
async def materialize_reports(
    *, client_id: Optional[int] = None, user_id: Optional[str] = None
) -> Dict[str, Any]:
    """(Re)materialize the persisted alert feed for one client or all clients.

    Delegates to ``routers.features._materialize_notifications`` (low-stock,
    stuck-ZATCA, overdue-subscription alerts), idempotent by ``dedupe_key``. With
    ``client_id`` it materializes one merchant; otherwise it sweeps every client.
    Runs in its own session and commits.
    """
    from sqlalchemy import select

    from core.database import db_manager
    from routers.features import _materialize_notifications

    await db_manager.ensure_initialized()
    materialized = 0
    async with db_manager.async_session_maker() as db:
        if client_id is not None and user_id is not None:
            await _materialize_notifications(db, str(user_id), int(client_id))
            materialized = 1
        else:
            from models.clients import Clients

            rows = (await db.execute(select(Clients.id, Clients.user_id))).all()
            for cid, uid in rows:
                if uid is None:
                    continue
                await _materialize_notifications(db, str(uid), int(cid))
                materialized += 1
        await db.commit()
    logger.info("Report materialization job complete: %d client(s)", materialized)
    return {"clients": materialized}


# ---------------------------------------------------------------------------
# Notification dispatch
# ---------------------------------------------------------------------------
@job("notification.dispatch")
async def dispatch_notification(
    *, user_id: str, type: str, title: str, message: str
) -> Dict[str, Any]:
    """Deliver one preference-honoring notification out-of-band (own session)."""
    from core.database import db_manager
    from services.notifications import NotificationDispatcher

    await db_manager.ensure_initialized()
    async with db_manager.async_session_maker() as db:
        return await NotificationDispatcher.dispatch(
            db, str(user_id), type=type, title=title, message=message
        )


# ---------------------------------------------------------------------------
# Catalog export
# ---------------------------------------------------------------------------
@job("export.generate")
async def generate_export(*, client_id: int) -> Dict[str, Any]:
    """Render a client's product catalog to CSV off the request path.

    Returns a summary (row count + byte size). The CSV itself is produced with
    the shared :func:`services.catalog_csv.products_to_csv` serializer so the
    queued export matches the synchronous one byte-for-byte; persisting it to
    object storage is the StorageService's job and out of scope here.
    """
    from sqlalchemy import select

    from core.database import db_manager
    from models.products import Products
    from services.catalog_csv import products_to_csv

    await db_manager.ensure_initialized()
    async with db_manager.async_session_maker() as db:
        products = (
            await db.execute(select(Products).where(Products.client_id == int(client_id)))
        ).scalars().all()
    csv_text = products_to_csv(products)
    summary = {"client_id": int(client_id), "rows": len(products), "bytes": len(csv_text.encode("utf-8"))}
    logger.info("Catalog export job complete: %s", summary)
    return summary
