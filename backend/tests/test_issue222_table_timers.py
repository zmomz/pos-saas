"""M6·Restaurant / issue-222: table timers.

The #222 acceptance criterion "timers ... apply": floor staff need to see how long
each occupied table has been seated so a turn-time target can be policed. The timer
reads from the ticket's ``opened_at`` against a clock, is owner-scoped (SEC-02),
excludes closed (settled/void) tickets, and flags any ticket seated past an optional
``over_minutes`` threshold (the floor-map "long-seated" alert).
"""
from datetime import datetime, timedelta

from sqlalchemy import select

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.restaurant import OrderTickets
from services.restaurant import RestaurantService


async def _make_table_with_ticket(client, token, name="T1"):
    """Place a table and open a dine-in ticket on it; return (table_id, ticket_id)."""
    headers = auth_headers(token)
    table_id = (
        await client.post(
            "/api/v1/restaurant/tables", json={"name": name, "seats": 4}, headers=headers
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


async def _set_opened_at(ticket_id: int, when: datetime) -> None:
    """Backdate a ticket's ``opened_at`` so the timer has a deterministic clock."""
    async with db_manager.async_session_maker() as db:
        tk = (
            await db.execute(select(OrderTickets).where(OrderTickets.id == ticket_id))
        ).scalar_one()
        tk.opened_at = when
        await db.commit()


# ---------------------------------------------------------------------------
# Behaviour 1: an active ticket reports its seated duration against a clock.
# ---------------------------------------------------------------------------
async def test_table_timer_reports_seated_duration(client):
    user, token, _cid = await make_client_account(client, business_type="restaurant")
    _table_id, ticket_id = await _make_table_with_ticket(client, token)

    opened = datetime(2026, 6, 30, 12, 0, 0)
    await _set_opened_at(ticket_id, opened)
    at = opened + timedelta(minutes=25, seconds=30)

    async with db_manager.async_session_maker() as db:
        timers = await RestaurantService(db).table_timers(user["id"], at=at)

    rows = {t["ticket_id"]: t for t in timers}
    assert ticket_id in rows
    row = rows[ticket_id]
    assert row["seated_seconds"] == 25 * 60 + 30
    assert row["seated_minutes"] == 25


# ---------------------------------------------------------------------------
# Behaviour 2: a closed (settled/void) ticket is off the floor — no timer.
# ---------------------------------------------------------------------------
async def test_table_timer_excludes_closed_tickets(client):
    user, token, _cid = await make_client_account(client, business_type="restaurant")
    _t1, open_ticket = await _make_table_with_ticket(client, token, name="T1")
    _t2, closed_ticket = await _make_table_with_ticket(client, token, name="T2")

    async with db_manager.async_session_maker() as db:
        tk = (
            await db.execute(select(OrderTickets).where(OrderTickets.id == closed_ticket))
        ).scalar_one()
        tk.status = "settled"
        await db.commit()

    async with db_manager.async_session_maker() as db:
        ids = {t["ticket_id"] for t in await RestaurantService(db).table_timers(user["id"])}

    assert open_ticket in ids
    assert closed_ticket not in ids


# ---------------------------------------------------------------------------
# Behaviour 3: timers are owner-scoped (SEC-02) — a foreign table never leaks.
# ---------------------------------------------------------------------------
async def test_table_timers_are_owner_scoped(client):
    user_a, token_a, _ca = await make_client_account(client, business_type="restaurant")
    user_b, token_b, _cb = await make_client_account(client, business_type="restaurant")
    _ta, ticket_a = await _make_table_with_ticket(client, token_a)
    _tb, ticket_b = await _make_table_with_ticket(client, token_b)

    async with db_manager.async_session_maker() as db:
        a_ids = {t["ticket_id"] for t in await RestaurantService(db).table_timers(user_a["id"])}

    assert ticket_a in a_ids
    assert ticket_b not in a_ids


# ---------------------------------------------------------------------------
# Behaviour 4: the floor endpoint flags tickets seated past ``over_minutes``.
# ---------------------------------------------------------------------------
async def test_table_timers_endpoint_flags_over_threshold(client):
    _user, token, _cid = await make_client_account(client, business_type="restaurant")
    _t1, long_ticket = await _make_table_with_ticket(client, token, name="Slow")
    _t2, fresh_ticket = await _make_table_with_ticket(client, token, name="Fresh")

    now = datetime.now()
    await _set_opened_at(long_ticket, now - timedelta(minutes=40))
    await _set_opened_at(fresh_ticket, now - timedelta(minutes=5))

    resp = await client.get(
        "/api/v1/restaurant/order-tickets/timers",
        params={"over_minutes": 30},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    rows = {t["ticket_id"]: t for t in resp.json()["items"]}

    assert rows[long_ticket]["is_over"] is True
    assert rows[long_ticket]["seated_minutes"] >= 40
    assert rows[fresh_ticket]["is_over"] is False
    # Longest-seated sorts first.
    assert resp.json()["items"][0]["ticket_id"] == long_ticket
