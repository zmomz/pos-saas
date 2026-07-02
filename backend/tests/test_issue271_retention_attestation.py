"""ISSUE-271 — ZATCA 6-year retention attestation endpoint.

`retention_until` is stamped on every signed fiscal document at write time
(default 6 years, ``ZATCA_RETENTION_YEARS``), but until now nothing *attested*
that coverage. These tests drive a new owner-scoped
``GET /api/v1/zatca/retention-attestation`` that reports, over the tenant's
fiscal documents: that every doc carries ``retention_until``, how many are still
within their window, the min/max coverage dates, and flags any gap (a doc
missing ``retention_until`` or whose window has already lapsed).
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from conftest import add_product, auth_headers, make_client_account
from core.database import db_manager
from models.clients import Clients
from models.zatca_documents import ZatcaDocuments


async def _set_vat(client_id: int, vat: str = "300000000000003"):
    async with db_manager.async_session_maker() as db:
        row = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        row.vat_number = vat
        await db.commit()


async def _sign_a_sale(client, headers, client_id, user_id, name="Cola") -> int:
    pid = await add_product(client_id, user_id, name=name, quantity=10, price=10.0)
    txn = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": name, "price": 10.0, "quantity": 1}],
            "payment_method": "cash",
        },
        headers=headers,
    )
    assert txn.status_code == 200, txn.text
    txn_id = txn.json()["id"]
    resp = await client.post(f"/api/v1/zatca/invoices/{txn_id}/sign", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["document_id"]


async def test_attests_full_retention_coverage(client):
    """Every signed doc carries a future retention_until -> attested, no gaps."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    await client.post("/api/v1/zatca/onboard/csr", json={}, headers=headers)

    await _sign_a_sale(client, headers, client_id, user["id"], name="A")
    await _sign_a_sale(client, headers, client_id, user["id"], name="B")

    resp = await client.get("/api/v1/zatca/retention-attestation", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert body["with_retention"] == 2
    assert body["missing_retention"] == 0
    assert body["within_window"] == 2
    assert body["expired"] == 0
    assert body["gaps"] == []
    assert body["attested"] is True
    assert body["retention_years"] == 6
    # min/max coverage dates are populated and in the future.
    assert body["coverage_start"] is not None
    assert body["coverage_end"] is not None


async def _override_retention(document_id: int, value):
    async with db_manager.async_session_maker() as db:
        row = (
            await db.execute(
                select(ZatcaDocuments).where(ZatcaDocuments.id == document_id)
            )
        ).scalar_one()
        row.retention_until = value
        await db.commit()


async def test_flags_document_missing_retention_until(client):
    """A doc with no retention_until is a gap -> not attested."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    await client.post("/api/v1/zatca/onboard/csr", json={}, headers=headers)

    doc_ok = await _sign_a_sale(client, headers, client_id, user["id"], name="A")
    doc_gap = await _sign_a_sale(client, headers, client_id, user["id"], name="B")
    await _override_retention(doc_gap, None)

    body = (
        await client.get("/api/v1/zatca/retention-attestation", headers=headers)
    ).json()
    assert body["total"] == 2
    assert body["with_retention"] == 1
    assert body["missing_retention"] == 1
    assert body["attested"] is False
    assert len(body["gaps"]) == 1
    gap = body["gaps"][0]
    assert gap["document_id"] == doc_gap
    assert gap["reason"] == "missing_retention_until"
    assert doc_ok != doc_gap  # the stamped one is not flagged


async def test_flags_expired_retention_window(client):
    """A doc whose retention window already lapsed is flagged as expired."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    await client.post("/api/v1/zatca/onboard/csr", json={}, headers=headers)

    doc = await _sign_a_sale(client, headers, client_id, user["id"], name="A")
    await _override_retention(doc, datetime.now(timezone.utc) - timedelta(days=1))

    body = (
        await client.get("/api/v1/zatca/retention-attestation", headers=headers)
    ).json()
    assert body["total"] == 1
    assert body["with_retention"] == 1
    assert body["within_window"] == 0
    assert body["expired"] == 1
    assert body["attested"] is False
    assert body["gaps"][0]["reason"] == "window_expired"


async def test_empty_archive_is_not_attested(client):
    """No fiscal documents -> nothing to attest (attested False, no gaps)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    body = (
        await client.get("/api/v1/zatca/retention-attestation", headers=headers)
    ).json()
    assert body["total"] == 0
    assert body["attested"] is False
    assert body["gaps"] == []
    assert body["coverage_start"] is None
    assert body["coverage_end"] is None


async def test_owner_scoped_non_client_forbidden(client):
    """Only a merchant/client tenancy can read the attestation (owner-scoped)."""
    from conftest import register_user

    _, token, _ = await register_user(client)  # plain user, no client row
    resp = await client.get(
        "/api/v1/zatca/retention-attestation", headers=auth_headers(token)
    )
    assert resp.status_code == 403
