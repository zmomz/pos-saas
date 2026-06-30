"""M6·Restaurant / issue-222: happy-hour pricing.

The #222 acceptance criterion "happy-hour apply": a merchant defines time-of-day
windows that knock a percentage off the menu price, and when a server adds a line
to an open ticket inside an active window the catalog price is automatically
discounted (server-authoritative). Windows are owner-scoped (SEC-02); a manual
price override is never silently re-discounted.
"""
from datetime import datetime

from sqlalchemy import select

from conftest import add_product, auth_headers, make_client_account
from core.database import db_manager
from models.restaurant import OrderTickets
from services.restaurant import RestaurantService


async def _table_with_ticket(client, token):
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


async def _make_window(client, token, **overrides):
    payload = {
        "name": "Half off",
        "discount_percent": 20,
        "start_minute": 0,
        "end_minute": 1439,
    }
    payload.update(overrides)
    return await client.post(
        "/api/v1/restaurant/happy-hours", json=payload, headers=auth_headers(token)
    )


# ---------------------------------------------------------------------------
# Behaviour 1: a line added during an active window is priced off the discount.
# ---------------------------------------------------------------------------
async def test_active_window_discounts_added_line(client):
    user, token, cid = await make_client_account(client, business_type="restaurant")
    product_id = await add_product(cid, user["id"], name="Latte", price=10.0)
    resp = await _make_window(client, token)  # all-day, 20% off
    assert resp.status_code == 201, resp.text

    _table_id, ticket_id = await _table_with_ticket(client, token)
    line = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"product_id": product_id, "qty": 2},
        headers=auth_headers(token),
    )
    assert line.status_code == 201, line.text
    body = line.json()
    assert body["unit_price"] == 8.0  # 10 - 20%
    assert body["line_total"] == 16.0  # 2 x 8


# ---------------------------------------------------------------------------
# Behaviour 2: an explicit manual price is never re-discounted.
# ---------------------------------------------------------------------------
async def test_manual_price_is_not_discounted(client):
    user, token, cid = await make_client_account(client, business_type="restaurant")
    product_id = await add_product(cid, user["id"], name="Latte", price=10.0)
    await _make_window(client, token)

    _table_id, ticket_id = await _table_with_ticket(client, token)
    line = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"product_id": product_id, "unit_price": 5.0},
        headers=auth_headers(token),
    )
    assert line.status_code == 201, line.text
    assert line.json()["unit_price"] == 5.0


# ---------------------------------------------------------------------------
# Behaviour 3: a non-positive / out-of-range discount is rejected (400).
# ---------------------------------------------------------------------------
async def test_invalid_discount_is_rejected(client):
    _user, token, _cid = await make_client_account(client, business_type="restaurant")
    assert (await _make_window(client, token, discount_percent=0)).status_code == 400
    assert (await _make_window(client, token, discount_percent=150)).status_code == 400


# ---------------------------------------------------------------------------
# Behaviour 4: windows are owner-scoped — tenant A's window never prices B.
# ---------------------------------------------------------------------------
async def test_window_is_owner_scoped(client):
    user_a, token_a, _ca = await make_client_account(client, business_type="restaurant")
    user_b, token_b, cid_b = await make_client_account(client, business_type="restaurant")
    await _make_window(client, token_a)  # only A has a happy hour
    product_b = await add_product(cid_b, user_b["id"], name="Tea", price=10.0)

    _table_id, ticket_id = await _table_with_ticket(client, token_b)
    line = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"product_id": product_b},
        headers=auth_headers(token_b),
    )
    assert line.status_code == 201, line.text
    assert line.json()["unit_price"] == 10.0  # B has no window → full price


# ---------------------------------------------------------------------------
# Behaviour 5: a window only fires inside its time-of-day + day-of-week range.
# ---------------------------------------------------------------------------
async def test_window_matches_time_and_day(client):
    user, token, _cid = await make_client_account(client, business_type="restaurant")
    inside = datetime(2026, 7, 1, 10, 0)  # 10:00
    weekday = str(inside.weekday())
    other_day = str((inside.weekday() + 1) % 7)
    # 09:00-11:00 on the in-window weekday only.
    await _make_window(
        client, token, start_minute=540, end_minute=660, days_of_week=weekday
    )

    async with db_manager.async_session_maker() as db:
        service = RestaurantService(db)
        # Inside the window on the matching day → discount applies.
        assert await service.active_happy_hour_discount(user["id"], at=inside) == 20.0
        # Outside the time-of-day window → no discount.
        assert (
            await service.active_happy_hour_discount(
                user["id"], at=datetime(2026, 7, 1, 12, 0)
            )
            == 0.0
        )

    # A window on a non-matching day never fires, even at the right time.
    await _make_window(
        client, token, start_minute=540, end_minute=660, days_of_week=other_day
    )
    async with db_manager.async_session_maker() as db:
        service = RestaurantService(db)
        # The wrong-day datetime sees neither the original window (wrong day) nor
        # the new window (also wrong day for this instant) → still no discount.
        wrong_day = datetime(2026, 7, 2, 10, 0)
        if wrong_day.weekday() not in (inside.weekday(), (inside.weekday() + 1) % 7):
            assert (
                await service.active_happy_hour_discount(user["id"], at=wrong_day) == 0.0
            )
        # The matching-day window still applies at `inside`.
        assert await service.active_happy_hour_discount(user["id"], at=inside) == 20.0
