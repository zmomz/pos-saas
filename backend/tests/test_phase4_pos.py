"""Phase 4 — POS feature completeness (shifts, offline sync on the atomic path).

Split-payment (POS-02) and loyalty (Phase E) already have coverage in
``test_phase_c_pos.py`` / ``test_phase_e_loyalty.py``. This suite proves the
remaining Phase 4 backend gaps are closed:

* a sale accumulates into the cashier's open shift and links via ``shift_id``;
* a refund nets back out of the open shift;
* ``GET /production/shifts/history`` lists closed shifts with reconciliation;
* the offline queue routes each sale through the **full** atomic path
  (inventory deduction + ECDSA signing) and is idempotent by ``offline_id``.
"""
from sqlalchemy import select

from conftest import (
    add_product,
    auth_headers,
    get_product_quantity,
    make_client_account,
)
from core.database import db_manager
from models.transactions import Transactions
from models.zatca_documents import ZatcaDocuments


async def _sale(client, headers, pid, *, price=10.0, qty=2):
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


async def _open_shift(client, headers, opening_cash=100.0):
    resp = await client.post(
        "/api/v1/production/shifts/open",
        json={"opening_cash": opening_cash},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Shifts: a sale accumulates into the open shift
# ---------------------------------------------------------------------------
async def test_sale_accumulates_into_open_shift(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=50, price=10.0)

    await _open_shift(client, headers)
    sale = await _sale(client, headers, pid, qty=2)  # 2*10 = 20 + 15% VAT = 23

    current = (await client.get("/api/v1/production/shifts/current", headers=headers)).json()
    assert current["status"] == "open"
    assert current["shift"]["total_transactions"] == 1
    assert abs(current["shift"]["total_sales"] - sale["total_amount"]) < 0.01

    # The transaction is linked to the shift.
    async with db_manager.async_session_maker() as db:
        txn = (
            await db.execute(select(Transactions).where(Transactions.id == sale["id"]))
        ).scalar_one()
        assert txn.shift_id == current["shift"]["id"]


async def test_sale_without_open_shift_succeeds_unlinked(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=10, price=10.0)

    sale = await _sale(client, headers, pid, qty=1)
    async with db_manager.async_session_maker() as db:
        txn = (
            await db.execute(select(Transactions).where(Transactions.id == sale["id"]))
        ).scalar_one()
        assert txn.shift_id is None


async def test_refund_nets_back_out_of_shift(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=50, price=10.0)

    await _open_shift(client, headers)
    sale = await _sale(client, headers, pid, qty=2)
    resp = await client.post(
        f"/api/v1/pos/transactions/{sale['id']}/refund", headers=headers
    )
    assert resp.status_code == 200, resp.text

    current = (await client.get("/api/v1/production/shifts/current", headers=headers)).json()
    # Sale + credit note net to zero; both counted as transactions.
    assert abs(current["shift"]["total_sales"]) < 0.01
    assert current["shift"]["total_transactions"] == 2


async def test_shift_history_lists_closed_shifts(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=50, price=10.0)

    await _open_shift(client, headers, opening_cash=200.0)
    sale = await _sale(client, headers, pid, qty=2)
    close = await client.post(
        "/api/v1/production/shifts/close",
        json={"closing_cash": 200.0 + sale["total_amount"]},
        headers=headers,
    )
    assert close.status_code == 200, close.text
    assert close.json()["reconciliation"] == "balanced"

    hist = (await client.get("/api/v1/production/shifts/history", headers=headers)).json()
    assert hist["total"] >= 1
    latest = hist["shifts"][0]
    assert latest["end_time"]  # only closed shifts are returned
    assert abs(latest["total_sales"] - sale["total_amount"]) < 0.01
    assert latest["total_transactions"] == 1


# ---------------------------------------------------------------------------
# Offline sync: full atomic path + idempotency (POS-05)
# ---------------------------------------------------------------------------
async def test_offline_sync_signs_deducts_and_dedupes(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=10, price=10.0)

    queued = {
        "offline_id": "OFFLINE-TEST-0001",
        "payment_method": "cash",
        "items": [{"product_id": pid, "name": "Cola", "price": 10.0, "quantity": 3}],
    }
    resp = await client.post(
        "/api/v1/production/offline/sync",
        json={"transactions": [queued]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["processed"] == 1 and body["skipped_duplicates"] == 0
    assert not body["errors"]

    # Inventory was deducted on the real path.
    assert await get_product_quantity(pid) == 7

    async with db_manager.async_session_maker() as db:
        txn = (
            await db.execute(
                select(Transactions).where(Transactions.offline_id == "OFFLINE-TEST-0001")
            )
        ).scalar_one()
        assert txn.invoice_number.startswith("INV-")  # real fiscal number, not OFFLINE-
        # The sale was ECDSA-signed and archived like any live sale.
        doc = (
            await db.execute(
                select(ZatcaDocuments).where(ZatcaDocuments.transaction_id == txn.id)
            )
        ).scalar_one()
        assert doc.stamp

    # Re-syncing the same queue is idempotent: skipped, stock unchanged.
    resp2 = await client.post(
        "/api/v1/production/offline/sync",
        json={"transactions": [queued]},
        headers=headers,
    )
    body2 = resp2.json()
    assert body2["processed"] == 0 and body2["skipped_duplicates"] == 1
    assert await get_product_quantity(pid) == 7
