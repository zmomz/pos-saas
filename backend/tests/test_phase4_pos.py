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


# ---------------------------------------------------------------------------
# Z-report / X-report (RPT-06, PRN-05, F-008): groups the shift by tender and
# reconciles cash against cash tenders only — not gross sales.
# ---------------------------------------------------------------------------
async def _card_sale(client, headers, pid, *, price=100.0, qty=1, method="mada"):
    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Combo", "price": price, "quantity": qty}],
            "payment_method": method,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_zreport_groups_by_tender_and_reconciles_variance(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    cash_pid = await add_product(client_id, user["id"], name="Cola", quantity=50, price=10.0)
    card_pid = await add_product(client_id, user["id"], name="Combo", quantity=50, price=100.0)

    open_resp = await _open_shift(client, headers, opening_cash=100.0)
    shift_id = open_resp["id"]

    cash_sale = await _sale(client, headers, cash_pid, qty=2)  # 2*10 + 15% = 23.00 (cash)
    await _card_sale(client, headers, card_pid, qty=1)         # 100 + 15% = 115.00 (mada)

    # Refund the cash sale in full → a credit note nets the cash back out.
    refund = await client.post(
        f"/api/v1/pos/transactions/{cash_sale['id']}/refund", headers=headers
    )
    assert refund.status_code == 200, refund.text

    # --- X-report (shift still open): no counted cash yet ---
    x = (await client.get("/api/v1/reports/zreport", headers=headers)).json()
    assert x["report_type"] == "X"
    tenders = {t["tender_type"]: t for t in x["tenders"]}
    assert abs(tenders["cash"]["amount"] - 23.0) < 0.01
    assert abs(tenders["mada"]["amount"] - 115.0) < 0.01
    assert abs(x["totals"]["gross_sales"] - 138.0) < 0.01
    assert abs(x["totals"]["refunds"] - 23.0) < 0.01
    assert abs(x["totals"]["net_sales"] - 115.0) < 0.01
    assert x["totals"]["refund_count"] == 1
    # Cash drawer counts cash tenders only (POS-09): opening + cash_sales − cash_refunds.
    assert abs(x["cash"]["expected_cash"] - 100.0) < 0.01
    assert x["cash"]["counted_cash"] is None
    assert x["cash"]["variance"] is None

    # --- Close, then the Z-report carries the counted cash + variance ---
    close = await client.post(
        "/api/v1/production/shifts/close",
        json={"closing_cash": 100.0},
        headers=headers,
    )
    assert close.status_code == 200, close.text

    z = (await client.get(f"/api/v1/reports/zreport?shift_id={shift_id}", headers=headers)).json()
    assert z["report_type"] == "Z"
    assert abs(z["cash"]["counted_cash"] - 100.0) < 0.01
    assert abs(z["cash"]["variance"]) < 0.01
    assert z["cash"]["reconciliation"] == "balanced"

    # The printable is an always-Arabic, non-fiscal management document (PRN-05).
    doc = await client.get(
        f"/api/v1/reports/zreport/document?shift_id={shift_id}", headers=headers
    )
    assert doc.status_code == 200, doc.text
    assert 'dir="rtl"' in doc.text
    assert "تقرير إغلاق الوردية" in doc.text  # Z-report title in Arabic
    assert "ليس فاتورة ضريبية" in doc.text     # "not a tax invoice"


async def test_close_shift_expected_cash_counts_cash_tenders_only(client):
    """POS-09 / F-009: closing the drawer must reconcile against CASH tenders
    only — not gross sales. With one cash sale (23) and one card/Mada sale (115),
    the expected drawer is opening + 23, NOT opening + 138. The cash-blind math
    (``opening + total_sales``) would expect 238 and report a 115 SAR shortfall."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    cash_pid = await add_product(client_id, user["id"], name="Cola", quantity=50, price=10.0)
    card_pid = await add_product(client_id, user["id"], name="Combo", quantity=50, price=100.0)

    await _open_shift(client, headers, opening_cash=100.0)
    await _sale(client, headers, cash_pid, qty=2)        # 2*10 + 15% = 23.00 (cash)
    await _card_sale(client, headers, card_pid, qty=1)   # 100 + 15% = 115.00 (mada)

    # Only the 23.00 cash leg ever entered the drawer.
    close = await client.post(
        "/api/v1/production/shifts/close",
        json={"closing_cash": 123.0},
        headers=headers,
    )
    assert close.status_code == 200, close.text
    body = close.json()
    assert abs(body["expected_cash"] - 123.0) < 0.01      # opening 100 + cash 23
    assert abs(body["cash_sales"] - 23.0) < 0.01
    assert abs(body["cash_refunds"]) < 0.01
    assert abs(body["cash_difference"]) < 0.01
    assert body["reconciliation"] == "balanced"
    # Gross sales are still tracked (and are NOT the drawer expectation).
    assert abs(body["total_sales"] - 138.0) < 0.01


async def test_close_shift_expected_cash_matches_zreport(client):
    """The close-time drawer math and the Z-report aggregator share one helper,
    so the stored shift and the printed Z-report must always agree (F-008/F-009)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    cash_pid = await add_product(client_id, user["id"], name="Cola", quantity=50, price=10.0)
    card_pid = await add_product(client_id, user["id"], name="Combo", quantity=50, price=100.0)

    open_resp = await _open_shift(client, headers, opening_cash=200.0)
    shift_id = open_resp["id"]
    await _sale(client, headers, cash_pid, qty=2)        # 23.00 cash
    await _card_sale(client, headers, card_pid, qty=1)   # 115.00 mada

    close = await client.post(
        "/api/v1/production/shifts/close",
        json={"closing_cash": 223.0},
        headers=headers,
    )
    assert close.status_code == 200, close.text

    z = (await client.get(f"/api/v1/reports/zreport?shift_id={shift_id}", headers=headers)).json()
    assert abs(z["cash"]["expected_cash"] - close.json()["expected_cash"]) < 0.01
    assert abs(z["cash"]["expected_cash"] - 223.0) < 0.01


async def test_zreport_scopes_to_owner_and_404s_unknown_shift(client):
    user_a, token_a, _ = await make_client_account(client)
    headers_a = auth_headers(token_a)
    await _open_shift(client, headers_a, opening_cash=50.0)
    a_shift = (await client.get("/api/v1/reports/zreport", headers=headers_a)).json()
    a_shift_id = a_shift["shift"]["id"]

    # A second client cannot read the first client's shift report.
    _, token_b, _ = await make_client_account(client)
    headers_b = auth_headers(token_b)
    cross = await client.get(
        f"/api/v1/reports/zreport?shift_id={a_shift_id}", headers=headers_b
    )
    assert cross.status_code == 404, cross.text
