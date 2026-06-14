"""Phase 6 — POS-08 audited void + permissioned price override (F-013).

A sale rung in error can be **voided**: an audited cancellation gated by the
``pos.void`` permission that marks the sale ``voided``, restores the deducted
stock, and writes an ``audit_logs`` row — distinct from a refund (which issues a
ZATCA credit note). A voided sale is excluded from revenue reports. A manual
unit-price change on the POS is gated by ``pos.price_override``.

Catches forever (per the COMPLETENESS_REVIEW F-013 finding):
* void without ``pos.void`` → 403; with it → status ``voided`` + an audit row;
* a voided sale drops out of the sales summary;
* void is owner-scoped (one client can't void another's sale);
* a fiscally-reported invoice can't be voided (409 — refund it instead);
* an overridden line price needs ``pos.price_override``.
"""
from sqlalchemy import select

from conftest import (
    add_product,
    auth_headers,
    get_product_quantity,
    make_client_account,
)
from core.database import db_manager
from models.audit_logs import Audit_logs
from models.permissions import Permissions
from models.transactions import Transactions
from models.zatca_documents import ZatcaDocuments


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _set_vat(client_id: int, vat: str = "300000000000003"):
    from models.clients import Clients

    async with db_manager.async_session_maker() as db:
        row = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        row.vat_number = vat
        await db.commit()


async def _set_permission(user_id: str, key: str, granted: bool):
    async with db_manager.async_session_maker() as db:
        existing = (
            await db.execute(
                select(Permissions).where(
                    Permissions.user_id == str(user_id),
                    Permissions.permission_key == key,
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.is_granted = granted
        else:
            db.add(
                Permissions(
                    user_id=str(user_id), permission_key=key, is_granted=granted
                )
            )
        await db.commit()


async def _sale(client, headers, pid, *, qty=2, price=10.0):
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


async def _txn_status(txn_id: int) -> str:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(select(Transactions.status).where(Transactions.id == txn_id))
        ).scalar_one()


async def _void_audit_rows(txn_id: int):
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(
                select(Audit_logs).where(
                    Audit_logs.action == "POS_VOID_SALE",
                    Audit_logs.entity_id == str(txn_id),
                )
            )
        ).scalars().all()


# ---------------------------------------------------------------------------
# Void: permission gate + audit + stock restore
# ---------------------------------------------------------------------------
async def test_void_denied_without_permission_then_voids(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=10.0)
    sale = await _sale(client, headers, pid, qty=2)

    # The sale deducted stock (10 - 2) and is a live completed sale.
    assert await get_product_quantity(pid) == 8
    assert await _txn_status(sale["id"]) == "completed"

    # Explicit deny → 403, and the sale is untouched (no audit, stock unchanged).
    await _set_permission(user["id"], "pos.void", granted=False)
    denied = await client.post(f"/api/v1/pos/transactions/{sale['id']}/void", headers=headers)
    assert denied.status_code == 403
    assert "pos.void" in denied.json()["detail"]
    assert await _txn_status(sale["id"]) == "completed"
    assert await get_product_quantity(pid) == 8
    assert await _void_audit_rows(sale["id"]) == []

    # Grant → 200: status flips to voided, stock is restored, an audit row exists.
    await _set_permission(user["id"], "pos.void", granted=True)
    ok = await client.post(
        f"/api/v1/pos/transactions/{sale['id']}/void",
        headers=headers,
        json={"reason": "wrong item"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "voided"
    assert await _txn_status(sale["id"]) == "voided"
    assert await get_product_quantity(pid) == 10
    rows = await _void_audit_rows(sale["id"])
    assert len(rows) == 1
    assert "wrong item" in (rows[0].details or "")

    # Idempotency: a second void is rejected.
    again = await client.post(f"/api/v1/pos/transactions/{sale['id']}/void", headers=headers)
    assert again.status_code == 400


async def test_voided_sale_excluded_from_sales_summary(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=10.0)
    sale = await _sale(client, headers, pid, qty=1)

    before = (await client.get("/api/v1/reports/sales-summary", headers=headers)).json()
    assert before["total_transactions"] == 1
    assert before["total_sales"] == sale["total_amount"]

    voided = await client.post(f"/api/v1/pos/transactions/{sale['id']}/void", headers=headers)
    assert voided.status_code == 200, voided.text

    after = (await client.get("/api/v1/reports/sales-summary", headers=headers)).json()
    assert after["total_transactions"] == 0
    assert after["total_sales"] == 0


async def test_void_is_owner_scoped(client):
    # Client A rings a sale; client B (a different tenant) cannot void it.
    user_a, token_a, client_a = await make_client_account(client)
    await _set_vat(client_a)
    pid = await add_product(client_a, user_a["id"], name="Cola", quantity=10, price=10.0)
    sale = await _sale(client, auth_headers(token_a), pid, qty=1)

    _user_b, token_b, _client_b = await make_client_account(client)
    # Client B is an account owner → holds pos.void by default, so the gate
    # passes and ownership scoping (not the permission) is what blocks them.
    resp = await client.post(
        f"/api/v1/pos/transactions/{sale['id']}/void", headers=auth_headers(token_b)
    )
    assert resp.status_code == 404
    # The sale is untouched on A's side.
    assert await _txn_status(sale["id"]) == "completed"


async def test_cannot_void_invoice_already_reported_to_zatca(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=10.0)
    sale = await _sale(client, headers, pid, qty=1)

    # Simulate ZATCA acceptance of the invoice.
    async with db_manager.async_session_maker() as db:
        doc = (
            await db.execute(
                select(ZatcaDocuments).where(ZatcaDocuments.transaction_id == sale["id"])
            )
        ).scalar_one()
        doc.status = "reported"
        await db.commit()

    resp = await client.post(f"/api/v1/pos/transactions/{sale['id']}/void", headers=headers)
    assert resp.status_code == 409
    assert "credit-note" in resp.json()["detail"].lower() or "credit note" in resp.json()["detail"].lower()
    # Still a live sale — it was not voided behind the compliance guard.
    assert await _txn_status(sale["id"]) == "completed"


# ---------------------------------------------------------------------------
# Price override: permission gate
# ---------------------------------------------------------------------------
async def test_price_override_requires_permission(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=50, price=10.0)

    # Deny the override permission for this cashier.
    await _set_permission(user["id"], "pos.price_override", granted=False)

    # A line at the catalog price is NOT an override → allowed even when denied.
    at_catalog = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 10.0, "quantity": 1}],
            "payment_method": "cash",
        },
        headers=headers,
    )
    assert at_catalog.status_code == 200, at_catalog.text

    # A line whose unit price differs from the catalog IS an override → 403.
    overridden = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 7.5, "quantity": 1}],
            "payment_method": "cash",
        },
        headers=headers,
    )
    assert overridden.status_code == 403
    assert "pos.price_override" in overridden.json()["detail"]

    # Grant it → the overridden price goes through.
    await _set_permission(user["id"], "pos.price_override", granted=True)
    allowed = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 7.5, "quantity": 1}],
            "payment_method": "cash",
        },
        headers=headers,
    )
    assert allowed.status_code == 200, allowed.text
