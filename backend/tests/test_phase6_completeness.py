"""Phase 6 — multi-branch, PDF, procurement.

Covers the Phase 6 backend gaps that are testable end-to-end:
* multi-branch: a sale carries its branch_id and the transaction list is
  branch-scoped, so per-branch sales reporting is isolated;
* PDF: the invoice endpoint returns real application/pdf bytes (%PDF header);
* procurement: receiving a purchase order increments product stock, records the
  receive date, advances status to 'received', and is idempotent.
"""
import json

from sqlalchemy import select

from conftest import (
    add_product,
    auth_headers,
    get_product_quantity,
    make_client_account,
)
from core.database import db_manager
from models.purchase_orders import Purchase_orders


async def _sale(client, headers, pid, *, qty=1, price=10.0, branch_id=None):
    payload = {
        "items": [{"product_id": pid, "name": "Cola", "price": price, "quantity": qty}],
        "payment_method": "cash",
    }
    if branch_id is not None:
        payload["branch_id"] = branch_id
    resp = await client.post("/api/v1/pos/transaction", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Multi-branch: branch-scoped sales reporting
# ---------------------------------------------------------------------------
async def test_sales_are_branch_scoped(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=100, price=10.0)

    await _sale(client, headers, pid, branch_id=1)
    await _sale(client, headers, pid, branch_id=1)
    await _sale(client, headers, pid, branch_id=2)

    branch1 = (
        await client.get("/api/v1/pos/transactions?branch_id=1", headers=headers)
    ).json()
    branch2 = (
        await client.get("/api/v1/pos/transactions?branch_id=2", headers=headers)
    ).json()
    all_txns = (await client.get("/api/v1/pos/transactions", headers=headers)).json()

    assert branch1["total"] == 2
    assert branch2["total"] == 1
    assert all_txns["total"] == 3  # unfiltered sees both branches


# ---------------------------------------------------------------------------
# PDF: invoice endpoint returns real PDF bytes
# ---------------------------------------------------------------------------
async def test_invoice_pdf_returns_pdf_bytes(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=10, price=10.0)
    sale = await _sale(client, headers, pid, qty=2)

    resp = await client.get(
        f"/api/v1/pos/transactions/{sale['id']}/pdf", headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"  # a real, openable PDF


# ---------------------------------------------------------------------------
# Procurement: receiving a PO increments inventory + is idempotent
# ---------------------------------------------------------------------------
async def test_receive_purchase_order_increments_stock(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=5, price=10.0)

    # Create a PO for 20 units of the product.
    po_resp = await client.post(
        "/api/v1/entities/purchase_orders",
        json={
            "client_id": client_id,
            "order_number": "PO-0001",
            "status": "pending",
            "items_json": json.dumps([{"product_id": pid, "quantity": 20, "cost": 4.5}]),
        },
        headers=headers,
    )
    assert po_resp.status_code == 201, po_resp.text
    po_id = po_resp.json()["id"]

    recv = await client.post(
        f"/api/v1/entities/purchase_orders/{po_id}/receive", headers=headers
    )
    assert recv.status_code == 200, recv.text
    body = recv.json()
    assert body["status"] == "received"
    assert body["received_items"] == 1

    # Stock went 5 -> 25.
    assert await get_product_quantity(pid) == 25

    async with db_manager.async_session_maker() as db:
        po = (
            await db.execute(select(Purchase_orders).where(Purchase_orders.id == po_id))
        ).scalar_one()
        assert po.received_date

    # Idempotent: a second receive is rejected, stock unchanged.
    recv2 = await client.post(
        f"/api/v1/entities/purchase_orders/{po_id}/receive", headers=headers
    )
    assert recv2.status_code == 400
    assert await get_product_quantity(pid) == 25
