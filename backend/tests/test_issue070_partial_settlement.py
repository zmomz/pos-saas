"""ISSUE-070 — Per-seat / partial settlement.

A restaurant ticket can be paid off in pieces — one seat now, the rest later, or
a specific item settled on its own. Each partial mints its **own** ZATCA-stamped
invoice through the exact same atomic sale core (``services.sale_core.execute_sale``)
a full settle uses, while the unpaid remainder of the ticket stays ``open`` (and
the table stays occupied). Settling the last of the remainder closes the ticket
and frees the table.

Coverage primitive: an explicit set of ticket items. **By item** passes
``item_ids``; **by seat** passes ``seat_no`` and the server resolves it to that
seat's still-unpaid items. ``OrderTicketItems.settled_at`` marks the lines a prior
partial already billed, so the check/split/settle paths all operate on the unpaid
remainder only — never double-billing a line.
"""
from sqlalchemy import func, select

from conftest import (
    add_product,
    auth_headers,
    get_product_quantity,
    make_client_account,
)
from core.database import db_manager
from models.clients import Clients
from models.transactions import Transactions
from models.zatca_documents import ZatcaDocuments


# ---------------------------------------------------------------------------
# Helpers (mirror test_phase5_rst_check_and_settle.py)
# ---------------------------------------------------------------------------
async def _set_vat(client_id: int, vat: str = "300000000000003"):
    async with db_manager.async_session_maker() as db:
        row = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        row.vat_number = vat
        await db.commit()


async def _make_table(client, token, name="T1"):
    return (
        await client.post(
            "/api/v1/restaurant/tables",
            json={"name": name, "seats": 4},
            headers=auth_headers(token),
        )
    ).json()["id"]


async def _open_dine_in(client, token, table_id):
    resp = await client.post(
        "/api/v1/restaurant/order-tickets",
        json={"order_type": "dine_in", "table_id": table_id},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _add_line(client, token, ticket_id, product_id, qty=1, seat_no=None):
    payload = {"product_id": product_id, "qty": qty}
    if seat_no is not None:
        payload["seat_no"] = seat_no
    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json=payload,
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _table_state(client, token, table_id) -> str:
    resp = await client.get(
        f"/api/v1/restaurant/tables/{table_id}", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["state"]


async def _ticket_status(client, token, ticket_id) -> str:
    resp = await client.get(
        f"/api/v1/restaurant/order-tickets/{ticket_id}", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["status"]


async def _txn_count(client_id: int) -> int:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(
                select(func.count(Transactions.id)).where(
                    Transactions.client_id == client_id
                )
            )
        ).scalar() or 0


# ---------------------------------------------------------------------------
# Tracer bullet: a partial settle by item mints a real ZATCA invoice for just
# that line and leaves the rest of the ticket open and the table occupied.
# ---------------------------------------------------------------------------
async def test_partial_settle_by_item_mints_invoice_and_keeps_ticket_open(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    await _set_vat(client_id)
    headers = auth_headers(token)
    table_id = await _make_table(client, token, name="P1")
    ticket_id = await _open_dine_in(client, token, table_id)
    a = await add_product(client_id, user["id"], name="Grill", quantity=20, price=100.0)
    b = await add_product(client_id, user["id"], name="Salad", quantity=20, price=40.0)
    line_a = await _add_line(client, token, ticket_id, a, qty=1)
    await _add_line(client, token, ticket_id, b, qty=1)

    # Pay just line A (the grill): 100 goods + 15 VAT = 115 due.
    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/settle-partial",
        json={"item_ids": [line_a["id"]], "payment_method": "cash"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # A real ZATCA invoice was minted for the settled subset via the sale core.
    assert body["invoice_number"].startswith(f"INV-{client_id:04d}-")
    assert body["zatca_document_id"] is not None
    assert body["zatca_status"] == "signed"
    assert body["zatca_qr"]
    assert abs(body["subtotal"] - 100.0) < 0.01
    assert abs(body["vat_amount"] - 15.0) < 0.01
    assert abs(body["amount_due"] - 115.0) < 0.01

    # The remainder is still open: ticket open, table occupied, not fully settled.
    assert body["fully_settled"] is False
    assert body["ticket_status"] == "open"
    assert body["table_freed"] is False
    assert await _ticket_status(client, token, ticket_id) == "open"
    assert await _table_state(client, token, table_id) == "occupied"

    # Exactly one fiscal sale so far, and only the settled item's stock moved.
    assert await _txn_count(client_id) == 1
    assert await get_product_quantity(a) == 19  # grill paid
    assert await get_product_quantity(b) == 20  # salad still on the open ticket


# ---------------------------------------------------------------------------
# By seat: settling a seat bills exactly that seat's lines; other seats remain.
# ---------------------------------------------------------------------------
async def test_partial_settle_by_seat_bills_that_seats_lines(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    await _set_vat(client_id)
    headers = auth_headers(token)
    table_id = await _make_table(client, token, name="P2")
    ticket_id = await _open_dine_in(client, token, table_id)
    a = await add_product(client_id, user["id"], name="Steak", quantity=20, price=80.0)
    b = await add_product(client_id, user["id"], name="Pasta", quantity=20, price=60.0)
    await _add_line(client, token, ticket_id, a, qty=1, seat_no=1)
    await _add_line(client, token, ticket_id, b, qty=1, seat_no=2)

    # Seat 1 pays: 80 goods + 12 VAT = 92 due — only seat 1's steak.
    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/settle-partial",
        json={"seat_no": 1, "payment_method": "cash"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert abs(body["subtotal"] - 80.0) < 0.01
    assert abs(body["amount_due"] - 92.0) < 0.01
    assert body["fully_settled"] is False
    assert body["ticket_status"] == "open"

    # Seat 1's stock moved; seat 2 is still on the open ticket.
    assert await get_product_quantity(a) == 19
    assert await get_product_quantity(b) == 20
    assert await _table_state(client, token, table_id) == "occupied"

    # The split now divides only the remainder — seat 2's pasta (60), not the steak.
    split = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/split",
        json={"strategy": "seat"},
        headers=headers,
    )
    assert split.status_code == 200, split.text
    assert abs(split.json()["total"] - 60.0) < 0.01


# ---------------------------------------------------------------------------
# Billing the last unpaid line closes the ticket and frees the table; the two
# partials' goods re-sum to the whole ticket — nothing billed twice or lost.
# ---------------------------------------------------------------------------
async def test_final_partial_closes_ticket_and_frees_table(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    await _set_vat(client_id)
    headers = auth_headers(token)
    table_id = await _make_table(client, token, name="P3")
    ticket_id = await _open_dine_in(client, token, table_id)
    a = await add_product(client_id, user["id"], name="Lamb", quantity=20, price=100.0)
    b = await add_product(client_id, user["id"], name="Rice", quantity=20, price=40.0)
    line_a = await _add_line(client, token, ticket_id, a, qty=1)
    line_b = await _add_line(client, token, ticket_id, b, qty=1)

    first = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/settle-partial",
        json={"item_ids": [line_a["id"]], "payment_method": "cash"},
        headers=headers,
    )
    assert first.status_code == 200, first.text
    assert first.json()["fully_settled"] is False
    assert await _ticket_status(client, token, ticket_id) == "open"

    # Pay the last unpaid line: the ticket closes and the table frees.
    second = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/settle-partial",
        json={"item_ids": [line_b["id"]], "payment_method": "cash"},
        headers=headers,
    )
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["fully_settled"] is True
    assert body["ticket_status"] == "settled"
    assert body["table_freed"] is True
    assert await _ticket_status(client, token, ticket_id) == "settled"
    assert await _table_state(client, token, table_id) == "free"

    # Two fiscal sales, and the two partials' goods re-sum to the full ticket (140).
    assert await _txn_count(client_id) == 2
    assert abs(first.json()["subtotal"] + body["subtotal"] - 140.0) < 0.01
    assert await get_product_quantity(a) == 19
    assert await get_product_quantity(b) == 19


# ---------------------------------------------------------------------------
# After a partial, the regular full /settle clears just the remainder and closes.
# ---------------------------------------------------------------------------
async def test_full_settle_after_partial_bills_only_remainder(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    await _set_vat(client_id)
    headers = auth_headers(token)
    table_id = await _make_table(client, token, name="P4")
    ticket_id = await _open_dine_in(client, token, table_id)
    a = await add_product(client_id, user["id"], name="Fish", quantity=20, price=100.0)
    b = await add_product(client_id, user["id"], name="Bread", quantity=20, price=40.0)
    line_a = await _add_line(client, token, ticket_id, a, qty=1)
    await _add_line(client, token, ticket_id, b, qty=1)

    partial = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/settle-partial",
        json={"item_ids": [line_a["id"]], "payment_method": "cash"},
        headers=headers,
    )
    assert partial.status_code == 200, partial.text

    # The ordinary full settle now charges only the unpaid remainder (bread: 40+6).
    full = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/settle",
        json={"payment_method": "cash"},
        headers=headers,
    )
    assert full.status_code == 200, full.text
    body = full.json()
    assert abs(body["subtotal"] - 40.0) < 0.01
    assert abs(body["amount_due"] - 46.0) < 0.01
    assert body["ticket_status"] == "settled"
    assert body["table_freed"] is True
    assert await _table_state(client, token, table_id) == "free"
    # Each product deducted exactly once across the partial + remainder.
    assert await get_product_quantity(a) == 19
    assert await get_product_quantity(b) == 19


# ---------------------------------------------------------------------------
# A line a prior partial already billed cannot be billed again (double-bill guard).
# ---------------------------------------------------------------------------
async def test_cannot_rebill_an_already_settled_item(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    await _set_vat(client_id)
    headers = auth_headers(token)
    table_id = await _make_table(client, token, name="P5")
    ticket_id = await _open_dine_in(client, token, table_id)
    a = await add_product(client_id, user["id"], name="Kofta", quantity=20, price=50.0)
    b = await add_product(client_id, user["id"], name="Hummus", quantity=20, price=20.0)
    line_a = await _add_line(client, token, ticket_id, a, qty=1)
    await _add_line(client, token, ticket_id, b, qty=1)

    first = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/settle-partial",
        json={"item_ids": [line_a["id"]], "payment_method": "cash"},
        headers=headers,
    )
    assert first.status_code == 200, first.text

    # Re-billing the same line is rejected — it's no longer an unpaid line.
    again = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/settle-partial",
        json={"item_ids": [line_a["id"]], "payment_method": "cash"},
        headers=headers,
    )
    assert again.status_code == 400, again.text
    # Only the one sale happened; the second line's stock is untouched.
    assert await _txn_count(client_id) == 1
    assert await get_product_quantity(a) == 19
    assert await get_product_quantity(b) == 20


# ---------------------------------------------------------------------------
# A declined card rolls the whole partial back: nothing billed, the chosen line
# stays on the open remainder (its settled mark and the close are staged in the
# same transaction execute_sale aborts).
# ---------------------------------------------------------------------------
async def test_declined_card_rolls_partial_back(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    await _set_vat(client_id)
    headers = auth_headers(token)
    table_id = await _make_table(client, token, name="P6")
    ticket_id = await _open_dine_in(client, token, table_id)
    a = await add_product(client_id, user["id"], name="Tagine", quantity=20, price=70.0)
    b = await add_product(client_id, user["id"], name="Olives", quantity=20, price=15.0)
    line_a = await _add_line(client, token, ticket_id, a, qty=1)
    await _add_line(client, token, ticket_id, b, qty=1)

    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/settle-partial",
        json={
            "item_ids": [line_a["id"]],
            "payment_method": "mada",
            "payment_simulate": "decline",
        },
        headers=headers,
    )
    assert resp.status_code == 402, resp.text

    # Nothing minted, the line is still unpaid, the ticket open, stock untouched.
    assert await _txn_count(client_id) == 0
    assert await _ticket_status(client, token, ticket_id) == "open"
    assert await _table_state(client, token, table_id) == "occupied"
    assert await get_product_quantity(a) == 20
    assert await get_product_quantity(b) == 20

    # The whole ticket (both lines) is still billable afterwards.
    full = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/settle",
        json={"payment_method": "cash"},
        headers=headers,
    )
    assert full.status_code == 200, full.text
    assert abs(full.json()["subtotal"] - 85.0) < 0.01
