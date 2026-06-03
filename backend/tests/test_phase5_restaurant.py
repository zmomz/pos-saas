"""Phase 5 — Restaurant vertical, first slice (F-045 / RST-01..03 + CL-02).

Proves the restaurant floor/table/order-ticket surface exists and is correctly
gated, which the whole vertical was missing (a restaurant client used to get a
404 on ``/api/v1/restaurant/tables``):

* a ``restaurant`` (or ``both``) client reaches ``/api/v1/restaurant/tables`` (200);
* a ``retail`` client is blocked (403) — the business_type discriminator works;
* disabling the per-client ``restaurant`` feature flag blocks it (403);
* tables/zones are owner-scoped (one client can't see another's floor, SEC-02);
* opening an order against a free table flips it to ``occupied`` and links the
  ticket; a second open-order on the same table is rejected (409).
"""
import uuid

from sqlalchemy import select

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.client_features import Client_features
from models.restaurant import OrderTickets, RestaurantTables


# ---------------------------------------------------------------------------
# The finding's named test: a restaurant client gets the route (today 404).
# ---------------------------------------------------------------------------
async def test_restaurant_tables_route_exists_for_restaurant_client(client):
    _user, token, _cid = await make_client_account(client, business_type="restaurant")
    resp = await client.get("/api/v1/restaurant/tables", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_business_type_both_can_reach_restaurant(client):
    _user, token, _cid = await make_client_account(client, business_type="both")
    resp = await client.get("/api/v1/restaurant/tables", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text


async def test_retail_client_is_blocked_from_restaurant(client):
    _user, token, _cid = await make_client_account(client, business_type="retail")
    resp = await client.get("/api/v1/restaurant/tables", headers=auth_headers(token))
    assert resp.status_code == 403, resp.text


async def test_disabled_restaurant_feature_blocks_even_a_restaurant_client(client):
    _user, token, client_id = await make_client_account(client, business_type="restaurant")
    # Agent explicitly turns the restaurant feature OFF for this client.
    async with db_manager.async_session_maker() as db:
        db.add(
            Client_features(
                user_id=str(uuid.uuid4()),
                client_id=client_id,
                feature_name="restaurant",
                is_enabled=False,
            )
        )
        await db.commit()

    resp = await client.get("/api/v1/restaurant/tables", headers=auth_headers(token))
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# CRUD + ownership scoping (SEC-02).
# ---------------------------------------------------------------------------
async def test_create_table_and_list(client):
    _user, token, _cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)

    created = await client.post(
        "/api/v1/restaurant/tables",
        json={"name": "T1", "seats": 4},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["state"] == "free"

    listing = await client.get("/api/v1/restaurant/tables", headers=headers)
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "T1"


async def test_tables_are_owner_scoped(client):
    _u1, token1, _c1 = await make_client_account(client, business_type="restaurant")
    _u2, token2, _c2 = await make_client_account(client, business_type="restaurant")

    await client.post(
        "/api/v1/restaurant/tables",
        json={"name": "OwnerOnly", "seats": 2},
        headers=auth_headers(token1),
    )

    # The second client must not see the first client's table.
    other = await client.get("/api/v1/restaurant/tables", headers=auth_headers(token2))
    assert other.status_code == 200
    assert other.json()["items"] == []


# ---------------------------------------------------------------------------
# Open-order flow: free -> occupied, link ticket, reject double-seat.
# ---------------------------------------------------------------------------
async def test_open_order_occupies_table_and_links_ticket(client):
    _user, token, _cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)

    table_id = (
        await client.post(
            "/api/v1/restaurant/tables", json={"name": "T9", "seats": 4}, headers=headers
        )
    ).json()["id"]

    opened = await client.post(
        f"/api/v1/restaurant/tables/{table_id}/open-order",
        json={"order_type": "dine_in", "party_size": 3},
        headers=headers,
    )
    assert opened.status_code == 201, opened.text
    ticket = opened.json()
    assert ticket["status"] == "open"
    assert ticket["table_id"] == table_id

    # The table is now occupied and points at the open ticket.
    async with db_manager.async_session_maker() as db:
        tbl = (
            await db.execute(select(RestaurantTables).where(RestaurantTables.id == table_id))
        ).scalar_one()
        assert tbl.state == "occupied"
        assert tbl.current_ticket_id == ticket["id"]
        tk = (
            await db.execute(select(OrderTickets).where(OrderTickets.id == ticket["id"]))
        ).scalar_one()
        assert tk.status == "open"
        assert tk.party_size == 3

    # A second open-order on the same (occupied) table is rejected.
    again = await client.post(
        f"/api/v1/restaurant/tables/{table_id}/open-order",
        json={"order_type": "dine_in"},
        headers=headers,
    )
    assert again.status_code == 409, again.text


async def test_open_order_rejects_unknown_order_type(client):
    _user, token, _cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    table_id = (
        await client.post(
            "/api/v1/restaurant/tables", json={"name": "T2"}, headers=headers
        )
    ).json()["id"]

    resp = await client.post(
        f"/api/v1/restaurant/tables/{table_id}/open-order",
        json={"order_type": "spaceship"},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
