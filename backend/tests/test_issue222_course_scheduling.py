"""M6·Restaurant / issue-222: course scheduling (coursing).

The #222 scope item "course scheduling": a server paces a multi-course meal by
scheduling when each course fires to the kitchen (starters now, mains in 15
minutes, dessert later) instead of firing every course by hand. A scheduled
course carries a ``fire_at`` time on its ticket; a sweep fires every course whose
time has come — advancing its open lines to ``fired`` exactly like a manual fire
(RST-02) — and leaves not-yet-due courses scheduled. Cancelling a schedule stops
the auto-fire. Owner-scoped (SEC-02).
"""
from datetime import datetime, timedelta

from conftest import auth_headers, make_client_account
from core.database import db_manager
from services.restaurant import RestaurantService


async def _open_ticket(client, token, name="T1"):
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
    return ticket_id


async def _add_line(client, token, ticket_id, course):
    headers = auth_headers(token)
    return (
        await client.post(
            f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
            json={"name": f"{course} dish", "qty": 1, "unit_price": 10, "course": course},
            headers=headers,
        )
    ).json()["id"]


# ---------------------------------------------------------------------------
# Behaviour 1: scheduling a course records its fire time and marks it scheduled.
# ---------------------------------------------------------------------------
async def test_schedule_course_records_fire_time(client):
    user, token, _cid = await make_client_account(client, business_type="restaurant")
    ticket_id = await _open_ticket(client, token)
    await _add_line(client, token, ticket_id, "mains")

    fire_at = datetime(2026, 6, 30, 20, 0, 0)
    async with db_manager.async_session_maker() as db:
        svc = RestaurantService(db)
        await svc.schedule_course(ticket_id, "mains", fire_at, user_id=user["id"])

    async with db_manager.async_session_maker() as db:
        rows = await RestaurantService(db).course_schedule_view(user["id"])

    by_course = {(r["ticket_id"], r["course"]): r for r in rows}
    assert (ticket_id, "mains") in by_course
    row = by_course[(ticket_id, "mains")]
    assert row["fire_at"].startswith("2026-06-30T20:00:00")
    assert row["state"] == "scheduled"


# ---------------------------------------------------------------------------
# Behaviour 2: the sweep fires due courses and skips not-yet-due ones.
# ---------------------------------------------------------------------------
async def test_fire_due_courses_fires_due_skips_future(client):
    user, token, _cid = await make_client_account(client, business_type="restaurant")
    ticket_id = await _open_ticket(client, token)
    starters_line = await _add_line(client, token, ticket_id, "starters")
    mains_line = await _add_line(client, token, ticket_id, "mains")

    base = datetime(2026, 6, 30, 19, 0, 0)
    async with db_manager.async_session_maker() as db:
        svc = RestaurantService(db)
        await svc.schedule_course(ticket_id, "starters", base, user_id=user["id"])
        await svc.schedule_course(
            ticket_id, "mains", base + timedelta(minutes=20), user_id=user["id"]
        )

    # Sweep at base + 5 min: starters are due, mains are not.
    async with db_manager.async_session_maker() as db:
        fired = await RestaurantService(db).fire_due_courses(
            user["id"], at=base + timedelta(minutes=5)
        )

    fired_courses = {f["course"] for f in fired}
    assert fired_courses == {"starters"}

    async with db_manager.async_session_maker() as db:
        items = {i.id: i for i in await RestaurantService(db).list_items(ticket_id, user["id"])}
    assert items[starters_line].fire_state == "fired"
    assert items[mains_line].fire_state == "open"

    # The due course is no longer scheduled; mains still is.
    async with db_manager.async_session_maker() as db:
        remaining = {
            r["course"] for r in await RestaurantService(db).course_schedule_view(user["id"])
        }
    assert remaining == {"mains"}


# ---------------------------------------------------------------------------
# Behaviour 3: cancelling a scheduled course stops the auto-fire.
# ---------------------------------------------------------------------------
async def test_cancel_course_schedule_prevents_autofire(client):
    user, token, _cid = await make_client_account(client, business_type="restaurant")
    ticket_id = await _open_ticket(client, token)
    line = await _add_line(client, token, ticket_id, "dessert")

    fire_at = datetime(2026, 6, 30, 18, 0, 0)
    async with db_manager.async_session_maker() as db:
        svc = RestaurantService(db)
        await svc.schedule_course(ticket_id, "dessert", fire_at, user_id=user["id"])

    async with db_manager.async_session_maker() as db:
        await RestaurantService(db).cancel_course_schedule(
            ticket_id, "dessert", user_id=user["id"]
        )

    async with db_manager.async_session_maker() as db:
        fired = await RestaurantService(db).fire_due_courses(
            user["id"], at=fire_at + timedelta(hours=1)
        )
    assert fired == []

    async with db_manager.async_session_maker() as db:
        items = {i.id: i for i in await RestaurantService(db).list_items(ticket_id, user["id"])}
    assert items[line].fire_state == "open"


# ---------------------------------------------------------------------------
# Behaviour 4: the sweep is owner-scoped — never fires a foreign ticket (SEC-02).
# ---------------------------------------------------------------------------
async def test_fire_due_courses_owner_scoped(client):
    user_a, token_a, _ca = await make_client_account(client, business_type="restaurant")
    user_b, token_b, _cb = await make_client_account(client, business_type="restaurant")
    ticket_b = await _open_ticket(client, token_b, name="B1")
    line_b = await _add_line(client, token_b, ticket_b, "mains")

    fire_at = datetime(2026, 6, 30, 17, 0, 0)
    async with db_manager.async_session_maker() as db:
        await RestaurantService(db).schedule_course(
            ticket_b, "mains", fire_at, user_id=user_b["id"]
        )

    # Owner A sweeps long after B's course is due — B's course must not fire.
    async with db_manager.async_session_maker() as db:
        fired = await RestaurantService(db).fire_due_courses(
            user_a["id"], at=fire_at + timedelta(hours=2)
        )
    assert fired == []

    async with db_manager.async_session_maker() as db:
        items = {i.id: i for i in await RestaurantService(db).list_items(ticket_b, user_b["id"])}
    assert items[line_b].fire_state == "open"


# ---------------------------------------------------------------------------
# Behaviour 5: the HTTP surface schedules a course and lists the schedule.
# ---------------------------------------------------------------------------
async def test_schedule_course_endpoint(client):
    _user, token, _cid = await make_client_account(client, business_type="restaurant")
    ticket_id = await _open_ticket(client, token)
    await _add_line(client, token, ticket_id, "mains")
    headers = auth_headers(token)

    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/schedule-course",
        json={"course": "mains", "fire_in_minutes": 15},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    listing = await client.get(
        "/api/v1/restaurant/order-tickets/course-schedule", headers=headers
    )
    assert listing.status_code == 200, listing.text
    rows = listing.json()["items"]
    mains = [r for r in rows if r["ticket_id"] == ticket_id and r["course"] == "mains"]
    assert len(mains) == 1
    assert mains[0]["seconds_remaining"] > 0
    assert mains[0]["is_due"] is False
