"""M6·Restaurant / issue-222: waiter (server) transfer on an order ticket.

The #222 acceptance criterion "waiter transfer works": a section's server can be
reassigned on an open ticket so the floor reflects who is now responsible for the
table. The server is one of the owner's own staff members; the reassignment is
owner-scoped (SEC-02) and transactional, and is rejected once the ticket is
settled/void (a closed bill no longer has a working section).
"""
import uuid

from sqlalchemy import select

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.restaurant import OrderTickets
from models.staff_members import Staff_members


async def _make_table_with_ticket(client, token):
    """Place a table and open a dine-in ticket on it; return (table_id, ticket_id)."""
    headers = auth_headers(token)
    table_id = (
        await client.post(
            "/api/v1/restaurant/tables", json={"name": "T1", "seats": 4}, headers=headers
        )
    ).json()["id"]
    ticket_id = (
        await client.post(
            f"/api/v1/restaurant/tables/{table_id}/open-order",
            json={"order_type": "dine_in"},
            headers=headers,
        )
    ).json()["id"]
    return table_id, ticket_id


async def _make_staff(owner_user_id: str, name: str = "Ava") -> int:
    """Insert a staff member owned by ``owner_user_id``; return its id."""
    async with db_manager.async_session_maker() as db:
        member = Staff_members(
            user_id=owner_user_id,
            name=name,
            role="waiter",
            is_active=True,
        )
        db.add(member)
        await db.commit()
        await db.refresh(member)
        return member.id


# ---------------------------------------------------------------------------
# Behaviour 1: transferring the waiter sets the ticket's server (id + name).
# ---------------------------------------------------------------------------
async def test_transfer_waiter_assigns_server_to_ticket(client):
    user, token, _cid = await make_client_account(client, business_type="restaurant")
    _table_id, ticket_id = await _make_table_with_ticket(client, token)
    server_id = await _make_staff(user["id"], name="Ava")

    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/transfer-waiter",
        json={"server_id": server_id},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["server_id"] == server_id
    assert body["server_name"] == "Ava"

    # Persisted on the ticket row.
    async with db_manager.async_session_maker() as db:
        tk = (
            await db.execute(select(OrderTickets).where(OrderTickets.id == ticket_id))
        ).scalar_one()
        assert tk.server_id == server_id
        assert tk.server_name == "Ava"


# ---------------------------------------------------------------------------
# Behaviour 2: an unknown / foreign staff member can't be assigned (SEC-02).
# ---------------------------------------------------------------------------
async def test_transfer_waiter_rejects_foreign_or_unknown_server(client):
    user_a, token_a, _ca = await make_client_account(client, business_type="restaurant")
    user_b, _token_b, _cb = await make_client_account(client, business_type="restaurant")
    _table_id, ticket_id = await _make_table_with_ticket(client, token_a)
    # A staff member belonging to *another* tenant.
    foreign_server = await _make_staff(user_b["id"], name="Mallory")

    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/transfer-waiter",
        json={"server_id": foreign_server},
        headers=auth_headers(token_a),
    )
    assert resp.status_code == 400, resp.text

    # An id that doesn't exist at all is rejected the same way.
    missing = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/transfer-waiter",
        json={"server_id": 999999},
        headers=auth_headers(token_a),
    )
    assert missing.status_code == 400, missing.text


async def test_transfer_waiter_on_foreign_ticket_is_404(client):
    _user_a, token_a, _ca = await make_client_account(client, business_type="restaurant")
    user_b, token_b, _cb = await make_client_account(client, business_type="restaurant")
    _table_id, ticket_id = await _make_table_with_ticket(client, token_a)
    # A valid server owned by B, so the 404 is proven to come from the ticket
    # scope (not the server validation).
    server_b = await _make_staff(user_b["id"])

    # Tenant B cannot see — or transfer the waiter on — tenant A's ticket.
    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/transfer-waiter",
        json={"server_id": server_b},
        headers=auth_headers(token_b),
    )
    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# Behaviour 3: the waiter can't be transferred on a closed (settled/void) ticket.
# ---------------------------------------------------------------------------
async def test_transfer_waiter_on_closed_ticket_is_409(client):
    user, token, _cid = await make_client_account(client, business_type="restaurant")
    _table_id, ticket_id = await _make_table_with_ticket(client, token)
    server_id = await _make_staff(user["id"])

    # Force the ticket closed (a real settle mints a fiscal invoice; this isolates
    # the closed-ticket guard).
    async with db_manager.async_session_maker() as db:
        tk = (
            await db.execute(select(OrderTickets).where(OrderTickets.id == ticket_id))
        ).scalar_one()
        tk.status = "void"
        await db.commit()

    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/transfer-waiter",
        json={"server_id": server_id},
        headers=auth_headers(token),
    )
    assert resp.status_code == 409, resp.text
