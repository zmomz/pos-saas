"""F-019 (ZA-08) — ZATCA document-status summary + stuck-doc alerting.

Proves the new ``GET /api/v1/zatca/documents/summary`` endpoint counts a
client's fiscal documents by status, flags stuck (pending/failed) documents for
attention, and is owner-scoped so one client never sees another's document
counts.
"""
import uuid

from sqlalchemy import select

from conftest import add_product, auth_headers, make_client_account, make_master_account
from core.database import db_manager
from models.clients import Clients
from models.zatca_documents import ZatcaDocuments


async def _set_vat(client_id: int, vat: str = "300000000000003"):
    async with db_manager.async_session_maker() as db:
        row = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        row.vat_number = vat
        await db.commit()


async def _set_statuses(client_id: int, statuses):
    """Force each of the client's documents to a status, in icv order.

    Deterministic — independent of the sale-time background reporting task.
    """
    async with db_manager.async_session_maker() as db:
        docs = (
            await db.execute(
                select(ZatcaDocuments)
                .where(ZatcaDocuments.client_id == client_id)
                .order_by(ZatcaDocuments.icv.asc())
            )
        ).scalars().all()
        for doc, st in zip(docs, statuses):
            doc.status = st
        await db.commit()


async def _sale(client, headers, pid, *, price=10.0, qty=1):
    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": price, "quantity": qty}],
            "payment_method": "cash",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_document_summary_counts_by_status_and_flags_stuck(client):
    """Three sales, forced to signed/pending/failed, summarize by status and flag
    the two stuck documents for attention (ZA-08)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=50, price=10.0)

    # Three B2C sales — each auto-signs a fiscal document.
    for _ in range(3):
        await _sale(client, headers, pid)

    # Force a deterministic spread: one signed (clean), one stuck pending, one failed.
    await _set_statuses(client_id, ["signed", "pending", "failed"])

    resp = await client.get("/api/v1/zatca/documents/summary", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total"] == 3
    assert body["by_status"]["signed"] == 1
    assert body["by_status"]["pending"] == 1
    assert body["by_status"]["failed"] == 1
    assert body["pending"] == 1
    assert body["failed"] == 1
    assert body["stuck"] == 2
    assert body["needs_attention"] is True
    # Default install is un-onboarded with no live gateway.
    assert body["onboarded"] is False


async def test_document_summary_no_stuck_documents_is_clean(client):
    """When every document is reported/cleared, needs_attention is False."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=50, price=10.0)

    await _sale(client, headers, pid)
    await _sale(client, headers, pid)
    await _set_statuses(client_id, ["reported", "cleared"])

    resp = await client.get("/api/v1/zatca/documents/summary", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert body["stuck"] == 0
    assert body["needs_attention"] is False


async def test_document_summary_is_owner_scoped(client):
    """One client's summary never counts another client's documents (SEC-02)."""
    user_a, token_a, client_a = await make_client_account(client)
    await _set_vat(client_a)
    pid_a = await add_product(client_a, user_a["id"], name="Cola", quantity=50, price=10.0)
    await _sale(client, auth_headers(token_a), pid_a)
    await _set_statuses(client_a, ["failed"])

    # A second, freshly-provisioned client has signed no documents.
    _user_b, token_b, _client_b = await make_client_account(client)

    resp_b = await client.get("/api/v1/zatca/documents/summary", headers=auth_headers(token_b))
    assert resp_b.status_code == 200, resp_b.text
    body_b = resp_b.json()
    assert body_b["total"] == 0
    assert body_b["stuck"] == 0
    assert body_b["needs_attention"] is False

    # Client A still sees their own stuck document.
    resp_a = await client.get("/api/v1/zatca/documents/summary", headers=auth_headers(token_a))
    assert resp_a.json()["stuck"] == 1


async def test_document_summary_requires_client_tenancy(client):
    """ZATCA is client-scoped — a non-client (master) gets 403."""
    _user, token = await make_master_account(client)
    resp = await client.get("/api/v1/zatca/documents/summary", headers=auth_headers(token))
    assert resp.status_code == 403
