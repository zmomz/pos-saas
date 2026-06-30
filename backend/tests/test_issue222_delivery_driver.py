"""M6·Restaurant / issue-222: delivery-driver assignment on an order ticket.

The #222 acceptance criterion "delivery-driver assignment": a delivery order can
be handed to one of the owner's own staff members (the driver) so dispatch knows
who is carrying the bag. The assignment is owner-scoped (SEC-02) and
transactional, only makes sense for a ``delivery`` order (a dine-in / takeaway
ticket has no driver), and is rejected once the ticket is settled/void.
"""
from sqlalchemy import select

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.restaurant import OrderTickets
from models.staff_members import Staff_members


async def _make_delivery_ticket(client, token):
    """Open a tableless delivery ticket; return its id."""
    resp = await client.post(
        "/api/v1/restaurant/order-tickets",
        json={"order_type": "delivery", "customer_name": "Sara"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _make_dine_in_ticket(client, token):
    """Place a table and open a dine-in ticket on it; return its id."""
    headers = auth_headers(token)
    table_id = (
        await client.post(
            "/api/v1/restaurant/tables", json={"name": "T1", "seats": 4}, headers=headers
        )
    ).json()["id"]
    return (
        await client.post(
            f"/api/v1/restaurant/tables/{table_id}/open-order",
            json={"order_type": "dine_in"},
            headers=headers,
        )
    ).json()["id"]


async def _make_staff(owner_user_id: str, name: str = "Karim") -> int:
    """Insert a staff member owned by ``owner_user_id``; return its id."""
    async with db_manager.async_session_maker() as db:
        member = Staff_members(
            user_id=owner_user_id, name=name, role="driver", is_active=True
        )
        db.add(member)
        await db.commit()
        await db.refresh(member)
        return member.id


async def _set_status(ticket_id: int, status: str) -> None:
    async with db_manager.async_session_maker() as db:
        tk = (
            await db.execute(select(OrderTickets).where(OrderTickets.id == ticket_id))
        ).scalar_one()
        tk.status = status
        await db.commit()


# ---------------------------------------------------------------------------
# Behaviour 1: assigning a driver sets the ticket's driver (id + name).
# ---------------------------------------------------------------------------
async def test_assign_driver_sets_driver_on_delivery_ticket(client):
    user, token, _cid = await make_client_account(client, business_type="restaurant")
    ticket_id = await _make_delivery_ticket(client, token)
    driver_id = await _make_staff(user["id"], name="Karim")

    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/assign-driver",
        json={"driver_id": driver_id},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["driver_id"] == driver_id
    assert body["driver_name"] == "Karim"

    async with db_manager.async_session_maker() as db:
        tk = (
            await db.execute(select(OrderTickets).where(OrderTickets.id == ticket_id))
        ).scalar_one()
        assert tk.driver_id == driver_id
        assert tk.driver_name == "Karim"


# ---------------------------------------------------------------------------
# Behaviour 2: a driver only makes sense on a delivery order.
# ---------------------------------------------------------------------------
async def test_assign_driver_rejects_non_delivery_ticket(client):
    user, token, _cid = await make_client_account(client, business_type="restaurant")
    dine_in_id = await _make_dine_in_ticket(client, token)
    driver_id = await _make_staff(user["id"])

    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{dine_in_id}/assign-driver",
        json={"driver_id": driver_id},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400, resp.text


# ---------------------------------------------------------------------------
# Behaviour 3: a foreign / unknown staff member can't be a driver (SEC-02).
# ---------------------------------------------------------------------------
async def test_assign_driver_rejects_foreign_or_unknown_staff(client):
    _user_a, token_a, _ca = await make_client_account(client, business_type="restaurant")
    user_b, _token_b, _cb = await make_client_account(client, business_type="restaurant")
    ticket_id = await _make_delivery_ticket(client, token_a)
    foreign_driver = await _make_staff(user_b["id"], name="Mallory")

    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/assign-driver",
        json={"driver_id": foreign_driver},
        headers=auth_headers(token_a),
    )
    assert resp.status_code == 400, resp.text

    missing = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/assign-driver",
        json={"driver_id": 999999},
        headers=auth_headers(token_a),
    )
    assert missing.status_code == 400, missing.text


# ---------------------------------------------------------------------------
# Behaviour 4: ticket scope (404) and closed-ticket rejection (409).
# ---------------------------------------------------------------------------
async def test_assign_driver_scope_and_closed_ticket(client):
    user_a, token_a, _ca = await make_client_account(client, business_type="restaurant")
    _user_b, token_b, _cb = await make_client_account(client, business_type="restaurant")
    ticket_id = await _make_delivery_ticket(client, token_a)
    driver_a = await _make_staff(user_a["id"])

    # Tenant B cannot see — or assign a driver on — tenant A's ticket.
    foreign = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/assign-driver",
        json={"driver_id": driver_a},
        headers=auth_headers(token_b),
    )
    assert foreign.status_code == 404, foreign.text

    # A settled bill has no driver to reassign.
    await _set_status(ticket_id, "settled")
    closed = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/assign-driver",
        json={"driver_id": driver_a},
        headers=auth_headers(token_a),
    )
    assert closed.status_code == 409, closed.text
