"""F-058 — Order types drive behavior (tableless takeaway / delivery + print routing).

Drives the order-type discriminator over HTTP (the real ASGI app):

* a takeaway or delivery order can be opened with **no table** via the new
  ``POST /order-tickets`` create path — the ticket carries ``table_id = None``;
* a dine-in order still **requires a table** (existing behavior preserved) and,
  when created through the same path, still occupies that table;
* ``order_type`` **drives print routing** — dine-in / takeaway / delivery each
  resolve to a different ordered list of print targets;
* the create + print-routing routes are owner-scoped (SEC-02) and behind the
  restaurant double-gate (a retail-only client gets 403).

The named "catch-forever" tests required by the slice are
``test_takeaway_order_needs_no_table`` and
``test_order_type_drives_print_routing``.
"""
from sqlalchemy import select

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.restaurant import RestaurantTables


async def _make_table(client, token, name="T1"):
    return (
        await client.post(
            "/api/v1/restaurant/tables", json={"name": name, "seats": 4}, headers=auth_headers(token)
        )
    ).json()["id"]


# ---------------------------------------------------------------------------
# Named slice test: a takeaway (and delivery) order needs no table.
# ---------------------------------------------------------------------------
async def test_takeaway_order_needs_no_table(client):
    _user, token, _cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)

    takeaway = await client.post(
        "/api/v1/restaurant/order-tickets",
        json={"order_type": "takeaway", "customer_name": "Walk-in"},
        headers=headers,
    )
    assert takeaway.status_code == 201, takeaway.text
    body = takeaway.json()
    assert body["order_type"] == "takeaway"
    assert body["table_id"] is None
    assert body["status"] == "open"

    delivery = await client.post(
        "/api/v1/restaurant/order-tickets",
        json={"order_type": "delivery", "customer_name": "Sara", "notes": "2nd floor"},
        headers=headers,
    )
    assert delivery.status_code == 201, delivery.text
    assert delivery.json()["order_type"] == "delivery"
    assert delivery.json()["table_id"] is None


async def test_dine_in_still_requires_a_table(client):
    """A dine-in order with no table is rejected (existing behavior preserved)."""
    _user, token, _cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)

    resp = await client.post(
        "/api/v1/restaurant/order-tickets",
        json={"order_type": "dine_in"},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text


async def test_dine_in_create_path_occupies_the_table(client):
    """Dine-in through the create path still flips the table to occupied."""
    _user, token, _cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    table_id = await _make_table(client, token, name="D1")

    resp = await client.post(
        "/api/v1/restaurant/order-tickets",
        json={"order_type": "dine_in", "table_id": table_id, "party_size": 3},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    ticket = resp.json()
    assert ticket["table_id"] == table_id

    async with db_manager.async_session_maker() as db:
        tbl = (
            await db.execute(select(RestaurantTables).where(RestaurantTables.id == table_id))
        ).scalar_one()
        assert tbl.state == "occupied"
        assert tbl.current_ticket_id == ticket["id"]


# ---------------------------------------------------------------------------
# Named slice test: order_type drives print routing.
# ---------------------------------------------------------------------------
async def test_order_type_drives_print_routing(client):
    _user, token, _cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    table_id = await _make_table(client, token, name="R1")

    dine_in = (
        await client.post(
            "/api/v1/restaurant/order-tickets",
            json={"order_type": "dine_in", "table_id": table_id},
            headers=headers,
        )
    ).json()["id"]
    takeaway = (
        await client.post(
            "/api/v1/restaurant/order-tickets",
            json={"order_type": "takeaway"},
            headers=headers,
        )
    ).json()["id"]
    delivery = (
        await client.post(
            "/api/v1/restaurant/order-tickets",
            json={"order_type": "delivery"},
            headers=headers,
        )
    ).json()["id"]

    routes = {}
    for tid in (dine_in, takeaway, delivery):
        resp = await client.get(
            f"/api/v1/restaurant/order-tickets/{tid}/print-routing", headers=headers
        )
        assert resp.status_code == 200, resp.text
        routes[tid] = resp.json()

    # Every order type routes to the kitchen...
    for payload in routes.values():
        assert "kitchen" in payload["targets"]

    # ...but the three order types route differently.
    dine_targets = routes[dine_in]["targets"]
    take_targets = routes[takeaway]["targets"]
    deliver_targets = routes[delivery]["targets"]
    assert routes[dine_in]["order_type"] == "dine_in"
    assert dine_targets != take_targets
    assert take_targets != deliver_targets
    assert dine_targets != deliver_targets
    # A dine-in prints a table check; takeaway/delivery do not.
    assert "table_check" in dine_targets
    assert "table_check" not in take_targets
    assert "delivery_docket" in deliver_targets


async def test_print_routing_owner_scoped(client):
    """A second client can't read the first client's print routing (SEC-02)."""
    _u1, token1, _cid1 = await make_client_account(client, business_type="restaurant")
    _u2, token2, _cid2 = await make_client_account(client, business_type="restaurant")
    ticket_id = (
        await client.post(
            "/api/v1/restaurant/order-tickets",
            json={"order_type": "takeaway"},
            headers=auth_headers(token1),
        )
    ).json()["id"]

    resp = await client.get(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/print-routing",
        headers=auth_headers(token2),
    )
    assert resp.status_code == 404, resp.text


async def test_create_ticket_requires_restaurant_business_type(client):
    """A retail-only client is blocked by the restaurant double-gate (403)."""
    _user, token, _cid = await make_client_account(client, business_type="retail")
    resp = await client.post(
        "/api/v1/restaurant/order-tickets",
        json={"order_type": "takeaway"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403, resp.text
