"""ISSUE-074 — Cash-drawer change-due helper (POS-13/F-... P2 POS).

On a cash payment the cashier enters the amount the customer handed over
(``cash_tendered``); the sale records it and the **change owed** back to the
customer (``change_due``). The change is purely informational/drawer-facing — it
never changes the invoice total, the VAT base, or the captured tender (the tender
covers the amount due, not the over-tendered cash).

Catches forever:
* a cash sale with cash tendered over the amount due returns + records the right
  change, while the invoice total / captured tender are unaffected;
* tendering less than the amount due is rejected (you can't under-pay cash);
* a sale with no cash_tendered carries no change (no façade field).
"""
from sqlalchemy import select

from conftest import add_product, auth_headers, make_client_account
from core.database import db_manager
from models.payment_tenders import PaymentTenders
from models.transactions import Transactions


async def _tender_amounts(txn_id: int):
    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(PaymentTenders).where(PaymentTenders.transaction_id == txn_id)
            )
        ).scalars().all()
        return {r.tender_type: r.amount for r in rows}


async def _stored(txn_id: int):
    async with db_manager.async_session_maker() as db:
        row = (
            await db.execute(
                select(Transactions.cash_tendered, Transactions.change_due).where(
                    Transactions.id == txn_id
                )
            )
        ).one()
        return row[0], row[1]


# ---------------------------------------------------------------------------
# Cash tendered over the amount due records the right change
# ---------------------------------------------------------------------------
async def test_cash_tendered_records_change_due(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=100.0)

    # Amount due is 115 (100 goods + 15 VAT); customer pays with a 200 note.
    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 100.0, "quantity": 1}],
            "payment_method": "cash",
            "cash_tendered": 200.0,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # The invoice total / VAT base are unaffected by the over-tender.
    assert abs(body["total_amount"] - 115.0) < 0.01
    # Change owed back = 200 - 115 = 85, surfaced on the response.
    assert abs(body["cash_tendered"] - 200.0) < 0.01
    assert abs(body["change_due"] - 85.0) < 0.01

    # Both are recorded on the sale row (not a label-only façade).
    tendered, change = await _stored(body["id"])
    assert abs(tendered - 200.0) < 0.01
    assert abs(change - 85.0) < 0.01

    # The captured tender covers the amount DUE (115), not the cash handed over.
    tenders = await _tender_amounts(body["id"])
    assert abs(tenders["cash"] - 115.0) < 0.01


async def test_sale_without_cash_tendered_has_no_change(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=100.0)

    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 100.0, "quantity": 1}],
            "payment_method": "cash",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["cash_tendered"] is None
    assert body["change_due"] is None


# ---------------------------------------------------------------------------
# Tendering less than the cash due is rejected
# ---------------------------------------------------------------------------
async def test_cash_tendered_below_due_rejected(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=100.0)

    # Amount due is 115; the customer hands over only 100 → rejected.
    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 100.0, "quantity": 1}],
            "payment_method": "cash",
            "cash_tendered": 100.0,
        },
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    assert "115" in resp.json()["detail"]
