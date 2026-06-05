"""F-055 — Order-ticket line items + course / fire / transfer / merge / split.

Drives the restaurant ticket lifecycle over HTTP (the real ASGI app):

* a server adds menu items to an open ticket with qty/course/seat/note;
* an *open* line can be removed but a *fired* line cannot be silently deleted;
* firing a course advances those lines to ``fired`` and stamps the ticket's
  ``course_state`` while a held course can still be fired later;
* transferring a ticket frees the source table and occupies the target;
* merging two tickets folds one into a single bill; splitting computes shares
  by seat, by amount, and by item;
* every operation is owner-scoped (SEC-02) — a second client can't touch the
  first client's ticket;
* the all-day fired-item count is queryable.

The named "catch-forever" tests required by the slice are
``test_add_items_by_course``, ``test_transfer_table_moves_ticket`` and
``test_split_bill_by_seat``.
"""
from sqlalchemy import select

from conftest import add_product, auth_headers, make_client_account
from core.database import db_manager
from models.restaurant import OrderTicketItems, RestaurantTables


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _open_ticket(client, token, table_name="T1"):
    """Create a table and open an order on it; return (table_id, ticket_id)."""
    headers = auth_headers(token)
    table_id = (
        await client.post(
            "/api/v1/restaurant/tables", json={"name": table_name, "seats": 4}, headers=headers
        )
    ).json()["id"]
    ticket_id = (
        await client.post(
            f"/api/v1/restaurant/tables/{table_id}/open-order",
            json={"order_type": "dine_in", "party_size": 2},
            headers=headers,
        )
    ).json()["id"]
    return table_id, ticket_id


# ---------------------------------------------------------------------------
# Named slice test: add items by course.
# ---------------------------------------------------------------------------
async def test_add_items_by_course(client):
    _user, token, cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    pid = await add_product(cid, _user["id"], name="Hummus", price=18.0, quantity=100)
    _tbl, ticket_id = await _open_ticket(client, token)

    starter = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"product_id": pid, "qty": 2, "course": "starters", "seat_no": 1, "notes": "no garlic"},
        headers=headers,
    )
    assert starter.status_code == 201, starter.text
    body = starter.json()
    # unit_price defaults to the catalog price; line_total is computed server-side.
    assert body["unit_price"] == 18.0
    assert body["line_total"] == 36.0
    assert body["course"] == "starters"
    assert body["seat_no"] == 1
    assert body["fire_state"] == "open"
    assert body["name"] == "Hummus"

    # A second line on a different course.
    await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"product_id": pid, "qty": 1, "course": "mains"},
        headers=headers,
    )

    listing = await client.get(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items", headers=headers
    )
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert len(items) == 2
    assert {i["course"] for i in items} == {"starters", "mains"}


async def test_line_persists_scoped_to_client(client):
    """An added line is owner-scoped — a second client can't read it (SEC-02)."""
    u1, token1, cid1 = await make_client_account(client, business_type="restaurant")
    _u2, token2, _cid2 = await make_client_account(client, business_type="restaurant")
    pid = await add_product(cid1, u1["id"], name="Tea", price=5.0)
    _tbl, ticket_id = await _open_ticket(client, token1)
    await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"product_id": pid, "qty": 1, "course": "mains"},
        headers=auth_headers(token1),
    )

    # Second client can't see or touch the first client's ticket/items.
    other = await client.get(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items", headers=auth_headers(token2)
    )
    assert other.status_code == 404, other.text


async def test_open_line_can_be_voided_but_fired_line_cannot(client):
    _user, token, cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    pid = await add_product(cid, _user["id"], name="Soup", price=12.0)
    _tbl, ticket_id = await _open_ticket(client, token)

    item_id = (
        await client.post(
            f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
            json={"product_id": pid, "qty": 1, "course": "starters"},
            headers=headers,
        )
    ).json()["id"]

    # While open it can be removed.
    voided = await client.delete(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items/{item_id}", headers=headers
    )
    assert voided.status_code == 200, voided.text

    # Add another and fire it; now it can't be silently deleted.
    item2 = (
        await client.post(
            f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
            json={"product_id": pid, "qty": 1, "course": "mains"},
            headers=headers,
        )
    ).json()["id"]
    fired = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/fire",
        json={"course": "mains"},
        headers=headers,
    )
    assert fired.status_code == 200, fired.text
    assert fired.json()["fired_count"] == 1

    blocked = await client.delete(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items/{item2}", headers=headers
    )
    assert blocked.status_code == 409, blocked.text


async def test_fire_course_advances_state_and_held_course_fires_later(client):
    _user, token, cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    pid = await add_product(cid, _user["id"], name="Plate", price=20.0)
    _tbl, ticket_id = await _open_ticket(client, token)

    for course in ("starters", "mains"):
        await client.post(
            f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
            json={"product_id": pid, "qty": 1, "course": course},
            headers=headers,
        )

    # Fire starters only — mains stays held.
    await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/fire",
        json={"course": "starters"},
        headers=headers,
    )
    ticket = (
        await client.get(f"/api/v1/restaurant/order-tickets/{ticket_id}", headers=headers)
    ).json()
    assert ticket["status"] == "fired"

    items = (
        await client.get(
            f"/api/v1/restaurant/order-tickets/{ticket_id}/items", headers=headers
        )
    ).json()["items"]
    by_course = {i["course"]: i["fire_state"] for i in items}
    assert by_course["starters"] == "fired"
    assert by_course["mains"] == "open"  # held

    # The held course fires later.
    later = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/fire",
        json={"course": "mains"},
        headers=headers,
    )
    assert later.status_code == 200
    assert later.json()["fired_count"] == 1


# ---------------------------------------------------------------------------
# Named slice test: transfer moves the ticket between tables.
# ---------------------------------------------------------------------------
async def test_transfer_table_moves_ticket(client):
    _user, token, cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    pid = await add_product(cid, _user["id"], name="Steak", price=80.0)

    src_table, ticket_id = await _open_ticket(client, token, table_name="A1")
    # A free target table.
    target_table = (
        await client.post(
            "/api/v1/restaurant/tables", json={"name": "B2", "seats": 2}, headers=headers
        )
    ).json()["id"]
    # Put a line on the ticket so we can prove it follows the move.
    await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"product_id": pid, "qty": 1, "course": "mains"},
        headers=headers,
    )

    moved = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/transfer",
        json={"target_table_id": target_table},
        headers=headers,
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["table_id"] == target_table

    async with db_manager.async_session_maker() as db:
        src = (
            await db.execute(select(RestaurantTables).where(RestaurantTables.id == src_table))
        ).scalar_one()
        tgt = (
            await db.execute(select(RestaurantTables).where(RestaurantTables.id == target_table))
        ).scalar_one()
        assert src.state == "free"
        assert src.current_ticket_id is None
        assert tgt.state == "occupied"
        assert tgt.current_ticket_id == ticket_id
        # The line followed the ticket.
        lines = (
            await db.execute(select(OrderTicketItems).where(OrderTicketItems.ticket_id == ticket_id))
        ).scalars().all()
        assert len(lines) == 1


async def test_transfer_to_occupied_table_is_rejected(client):
    _user, token, _cid = await make_client_account(client, business_type="restaurant")
    _src, ticket_id = await _open_ticket(client, token, table_name="C1")
    _busy_table, _busy_ticket = await _open_ticket(client, token, table_name="C2")
    # C2 is occupied; transferring onto it must fail.
    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/transfer",
        json={"target_table_id": _busy_table},
        headers=auth_headers(token),
    )
    assert resp.status_code == 409, resp.text


async def test_merge_tickets_into_one_bill(client):
    _user, token, cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    pid = await add_product(cid, _user["id"], name="Juice", price=10.0)

    src_table, source_ticket = await _open_ticket(client, token, table_name="M1")
    _tgt_table, target_ticket = await _open_ticket(client, token, table_name="M2")
    for tk in (source_ticket, target_ticket):
        await client.post(
            f"/api/v1/restaurant/order-tickets/{tk}/items",
            json={"product_id": pid, "qty": 1, "course": "mains"},
            headers=headers,
        )

    merged = await client.post(
        f"/api/v1/restaurant/order-tickets/{target_ticket}/merge",
        json={"source_ticket_id": source_ticket},
        headers=headers,
    )
    assert merged.status_code == 200, merged.text

    # Target now holds both lines.
    items = (
        await client.get(
            f"/api/v1/restaurant/order-tickets/{target_ticket}/items", headers=headers
        )
    ).json()["items"]
    assert len(items) == 2

    # Source ticket is voided and its table freed.
    src_ticket = (
        await client.get(f"/api/v1/restaurant/order-tickets/{source_ticket}", headers=headers)
    ).json()
    assert src_ticket["status"] == "void"
    async with db_manager.async_session_maker() as db:
        src = (
            await db.execute(select(RestaurantTables).where(RestaurantTables.id == src_table))
        ).scalar_one()
        assert src.state == "free"
        assert src.current_ticket_id is None


# ---------------------------------------------------------------------------
# Named slice test: split a bill by seat (and amount and item).
# ---------------------------------------------------------------------------
async def test_split_bill_by_seat(client):
    _user, token, cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    pid = await add_product(cid, _user["id"], name="Burger", price=25.0)
    _tbl, ticket_id = await _open_ticket(client, token)

    # Seat 1 has two items (50), seat 2 has one (25).
    await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"product_id": pid, "qty": 2, "course": "mains", "seat_no": 1},
        headers=headers,
    )
    await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"product_id": pid, "qty": 1, "course": "mains", "seat_no": 2},
        headers=headers,
    )

    by_seat = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/split",
        json={"strategy": "seat"},
        headers=headers,
    )
    assert by_seat.status_code == 200, by_seat.text
    payload = by_seat.json()
    assert payload["total"] == 75.0
    shares = {s["seat"]: s["subtotal"] for s in payload["shares"]}
    assert shares["1"] == 50.0
    assert shares["2"] == 25.0

    # By amount — two equal shares re-summing to the total.
    by_amount = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/split",
        json={"strategy": "amount", "n_ways": 2},
        headers=headers,
    )
    amounts = [s["subtotal"] for s in by_amount.json()["shares"]]
    assert len(amounts) == 2
    assert round(sum(amounts), 2) == 75.0

    # By item — one share per line.
    by_item = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/split",
        json={"strategy": "item"},
        headers=headers,
    )
    assert len(by_item.json()["shares"]) == 2


async def test_all_day_fired_count(client):
    _user, token, cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    pid = await add_product(cid, _user["id"], name="Fries", price=8.0)
    _tbl, ticket_id = await _open_ticket(client, token)

    await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"product_id": pid, "qty": 3, "course": "mains"},
        headers=headers,
    )
    # Unfired items are not counted.
    pre = await client.get("/api/v1/restaurant/all-day-count", headers=headers)
    assert pre.json()["fired_item_count"] == 0

    await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/fire",
        json={"course": "mains"},
        headers=headers,
    )
    post = await client.get("/api/v1/restaurant/all-day-count", headers=headers)
    body = post.json()
    assert body["fired_item_count"] == 1
    assert body["fired_qty"] == 3.0


async def test_ticket_items_owner_scoped_on_mutation(client):
    """A second client can't add a line to the first client's ticket (SEC-02)."""
    u1, token1, cid1 = await make_client_account(client, business_type="restaurant")
    _u2, token2, _cid2 = await make_client_account(client, business_type="restaurant")
    pid = await add_product(cid1, u1["id"], name="Cake", price=15.0)
    _tbl, ticket_id = await _open_ticket(client, token1)

    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"product_id": pid, "qty": 1, "course": "dessert"},
        headers=auth_headers(token2),
    )
    assert resp.status_code == 404, resp.text
