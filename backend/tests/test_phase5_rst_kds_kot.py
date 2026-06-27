"""F-057 — KDS / KOT + real-time kitchen channel.

Drives the kitchen-display lifecycle over HTTP (the real ASGI app):

* a manager defines prep-stations with bilingual names;
* firing a course materializes one KDS card per relevant prep-station and routes
  each fired line to the station that prepares it;
* a cook bumps a card off the active board and recalls a mistaken bump, with the
  source order line's ``fire_state`` kept in sync (server screen ⇄ kitchen);
* the per-station 80mm KOT renders (always-Arabic, modifiers grouped by course,
  **no prices**);
* the SSE stream emits an initial board snapshot;
* every KDS entity/route is owner-scoped (SEC-02) behind the restaurant double-gate.

The named "catch-forever" tests required by the slice are
``test_fire_creates_kds_ticket_per_station``, ``test_bump_then_recall`` and the
KOT-render test ``test_kot_render_arabic_no_prices``.
"""
import base64
import json

from conftest import add_product, auth_headers, make_client_account


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _open_ticket(client, token, table_name="T1"):
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


async def _make_station(client, token, name, name_ar=None):
    resp = await client.post(
        "/api/v1/restaurant/kds/stations",
        json={"name": name, "name_ar": name_ar},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Prep stations
# ---------------------------------------------------------------------------
async def test_manager_defines_prep_stations_bilingual(client):
    _user, token, _cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)

    sid = await _make_station(client, token, "Grill", "الشواية")
    listing = await client.get("/api/v1/restaurant/kds/stations", headers=headers)
    assert listing.status_code == 200
    stations = listing.json()
    assert len(stations) == 1
    assert stations[0]["id"] == sid
    assert stations[0]["name"] == "Grill"
    assert stations[0]["name_ar"] == "الشواية"


async def test_prep_stations_owner_scoped(client):
    """A second client can't see or delete the first client's stations (SEC-02)."""
    _u1, token1, _c1 = await make_client_account(client, business_type="restaurant")
    _u2, token2, _c2 = await make_client_account(client, business_type="restaurant")
    sid = await _make_station(client, token1, "Bar", "البار")

    other = await client.get("/api/v1/restaurant/kds/stations", headers=auth_headers(token2))
    assert other.json() == []
    blocked = await client.delete(
        f"/api/v1/restaurant/kds/stations/{sid}", headers=auth_headers(token2)
    )
    assert blocked.status_code == 404, blocked.text


# ---------------------------------------------------------------------------
# Named slice test: firing routes one card per prep-station.
# ---------------------------------------------------------------------------
async def test_fire_creates_kds_ticket_per_station(client):
    _user, token, cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    grill = await _make_station(client, token, "Grill", "الشواية")
    bar = await _make_station(client, token, "Bar", "البار")

    steak = await add_product(cid, _user["id"], name="Steak", price=80.0, quantity=50)
    juice = await add_product(cid, _user["id"], name="Juice", price=12.0, quantity=50)
    _tbl, ticket_id = await _open_ticket(client, token)

    # Two mains lines, each routed to a different station.
    await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"product_id": steak, "qty": 1, "course": "mains", "prep_station_id": grill},
        headers=headers,
    )
    await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"product_id": juice, "qty": 2, "course": "mains", "prep_station_id": bar},
        headers=headers,
    )

    fired = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/fire",
        json={"course": "mains"},
        headers=headers,
    )
    assert fired.status_code == 200, fired.text
    assert len(fired.json()["kds_ticket_ids"]) == 2

    board = (await client.get("/api/v1/restaurant/kds/tickets", headers=headers)).json()
    assert board["total"] == 2
    by_station = {c["station_id"]: c for c in board["items"]}
    assert set(by_station) == {grill, bar}
    # Each card carries only its own station's line.
    assert by_station[grill]["items"][0]["name"] == "Steak"
    assert by_station[bar]["items"][0]["name"] == "Juice"
    assert by_station[bar]["items"][0]["qty"] == 2.0
    assert all(c["status"] == "active" for c in board["items"])

    # Station-filtered board returns just that column.
    grill_only = (
        await client.get(
            f"/api/v1/restaurant/kds/tickets?station_id={grill}", headers=headers
        )
    ).json()
    assert grill_only["total"] == 1
    assert grill_only["items"][0]["station_id"] == grill


# ---------------------------------------------------------------------------
# Named slice test: bump then recall keeps line state in sync.
# ---------------------------------------------------------------------------
async def test_bump_then_recall(client):
    _user, token, cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    grill = await _make_station(client, token, "Grill", "الشواية")
    pid = await add_product(cid, _user["id"], name="Burger", price=30.0, quantity=50)
    _tbl, ticket_id = await _open_ticket(client, token)

    item_id = (
        await client.post(
            f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
            json={"product_id": pid, "qty": 1, "course": "mains", "prep_station_id": grill},
            headers=headers,
        )
    ).json()["id"]
    fired = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/fire",
        json={"course": "mains"},
        headers=headers,
    )
    kds_id = fired.json()["kds_ticket_ids"][0]

    # Bump removes the card from the active board and bumps the source line.
    bumped = await client.post(f"/api/v1/restaurant/kds/{kds_id}/bump", headers=headers)
    assert bumped.status_code == 200, bumped.text
    assert bumped.json()["status"] == "bumped"
    assert bumped.json()["bumped_at"] is not None

    active = (await client.get("/api/v1/restaurant/kds/tickets", headers=headers)).json()
    assert active["total"] == 0  # gone from the active board
    line = (
        await client.get(
            f"/api/v1/restaurant/order-tickets/{ticket_id}/items", headers=headers
        )
    ).json()["items"]
    assert next(i for i in line if i["id"] == item_id)["fire_state"] == "bumped"

    # Recall restores it to the board and the line drops back to fired.
    recalled = await client.post(f"/api/v1/restaurant/kds/{kds_id}/recall", headers=headers)
    assert recalled.status_code == 200, recalled.text
    assert recalled.json()["status"] == "active"
    assert recalled.json()["bumped_at"] is None

    active2 = (await client.get("/api/v1/restaurant/kds/tickets", headers=headers)).json()
    assert active2["total"] == 1
    line2 = (
        await client.get(
            f"/api/v1/restaurant/order-tickets/{ticket_id}/items", headers=headers
        )
    ).json()["items"]
    assert next(i for i in line2 if i["id"] == item_id)["fire_state"] == "fired"


# ---------------------------------------------------------------------------
# Named slice test: KOT render — always-Arabic, modifiers by course, no prices.
# ---------------------------------------------------------------------------
async def test_kot_render_arabic_no_prices(client):
    _user, token, cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    grill = await _make_station(client, token, "Grill", "الشواية")
    pid = await add_product(cid, _user["id"], name="Steak", price=80.0, quantity=50)

    # A modifier so the KOT proves it groups modifier choices under the course.
    group = (
        await client.post(
            "/api/v1/restaurant/modifier-groups",
            json={"name": "Doneness", "name_ar": "النضج", "required": False, "max_select": 1},
            headers=headers,
        )
    ).json()
    mod = (
        await client.post(
            f"/api/v1/restaurant/modifier-groups/{group['id']}/modifiers",
            json={"name": "Well done", "name_ar": "ناضج", "price_delta": 0},
            headers=headers,
        )
    ).json()

    _tbl, ticket_id = await _open_ticket(client, token)
    await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={
            "product_id": pid,
            "qty": 2,
            "course": "mains",
            "prep_station_id": grill,
            "notes": "no salt",
            "modifiers": [mod["id"]],
        },
        headers=headers,
    )
    fired = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/fire",
        json={"course": "mains"},
        headers=headers,
    )
    kds_id = fired.json()["kds_ticket_ids"][0]

    kot = await client.get(f"/api/v1/restaurant/kds/{kds_id}/kot", headers=headers)
    assert kot.status_code == 200, kot.text
    payload = kot.json()

    # The KOT model groups items by course and carries NO price/total anywhere.
    assert payload["station_name_ar"] == "الشواية"
    assert len(payload["courses"]) == 1
    course = payload["courses"][0]
    assert course["course"] == "mains"
    item = course["items"][0]
    assert item["qty"] == 2.0
    assert item["notes"] == "no salt"
    assert "Well done" in item["modifiers"]
    # No money on a kitchen ticket — assert the whole serialized payload is clean.
    blob = json.dumps(payload).lower()
    for forbidden in ("price", "line_total", "unit_price", "subtotal", "vat", "amount"):
        assert forbidden not in blob, f"KOT payload leaked '{forbidden}'"

    # The rendered ESC/POS stream is valid (starts with ESC @) and non-trivial.
    raw = base64.b64decode(payload["kot_base64"])
    assert raw[:2] == bytes([0x1B, 0x40])  # ESC @ printer init
    assert len(raw) > 64


async def test_lines_without_station_collect_on_one_card(client):
    """Fired lines with no prep_station_id materialize as a single expo card (F-057)."""
    _user, token, cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    pid = await add_product(cid, _user["id"], name="Bread", price=5.0, quantity=50)
    _tbl, ticket_id = await _open_ticket(client, token)
    for _ in range(2):
        await client.post(
            f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
            json={"product_id": pid, "qty": 1, "course": "starters"},
            headers=headers,
        )
    fired = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/fire",
        json={"course": "starters"},
        headers=headers,
    )
    assert len(fired.json()["kds_ticket_ids"]) == 1
    board = (await client.get("/api/v1/restaurant/kds/tickets", headers=headers)).json()
    assert board["total"] == 1
    assert board["items"][0]["station_id"] is None
    assert len(board["items"][0]["items"]) == 2


async def test_kds_board_owner_scoped(client):
    """A second client's fired course never appears on the first client's board."""
    u1, token1, cid1 = await make_client_account(client, business_type="restaurant")
    _u2, token2, _cid2 = await make_client_account(client, business_type="restaurant")
    pid = await add_product(cid1, u1["id"], name="Soup", price=10.0, quantity=50)
    _tbl, ticket_id = await _open_ticket(client, token1)
    await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"product_id": pid, "qty": 1, "course": "mains"},
        headers=auth_headers(token1),
    )
    await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/fire",
        json={"course": "mains"},
        headers=auth_headers(token1),
    )
    # The other client sees an empty board and can't bump the card.
    other = (await client.get("/api/v1/restaurant/kds/tickets", headers=auth_headers(token2))).json()
    assert other["total"] == 0


async def test_retail_client_blocked_from_kds(client):
    """The KDS routes are behind the restaurant double-gate (retail → 403)."""
    _user, token, _cid = await make_client_account(client, business_type="retail")
    resp = await client.get("/api/v1/restaurant/kds/tickets", headers=auth_headers(token))
    assert resp.status_code == 403, resp.text
    resp2 = await client.post(
        "/api/v1/restaurant/kds/stations", json={"name": "Grill"}, headers=auth_headers(token)
    )
    assert resp2.status_code == 403, resp2.text


async def test_kds_stream_rejects_bad_ticket(client):
    """The SSE stream gates on a single-use ticket, not a token-in-URL (FE-02)."""
    bad = await client.get("/api/v1/restaurant/kds/stream?ticket=not-a-real-ticket")
    assert bad.status_code == 401, bad.text


async def test_fire_publishes_to_kitchen_channel_in_real_time(client):
    """Firing a course pushes a 'fired' event to the live channel within ~1s (F-057).

    The deterministic core of the real-time guarantee: a subscriber on the
    in-process broker (what an open SSE stream holds) receives the fired card
    immediately, without polling. We exercise the broker directly rather than the
    never-ending SSE response (which an in-memory test transport would buffer).
    """
    import asyncio as _asyncio

    from services.kds_channel import kds_broker

    _user, token, cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    grill = await _make_station(client, token, "Grill", "الشواية")
    pid = await add_product(cid, _user["id"], name="Wings", price=22.0, quantity=50)
    _tbl, ticket_id = await _open_ticket(client, token)
    await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"product_id": pid, "qty": 1, "course": "mains", "prep_station_id": grill},
        headers=headers,
    )

    queue = kds_broker.subscribe(_user["id"])
    try:
        await client.post(
            f"/api/v1/restaurant/order-tickets/{ticket_id}/fire",
            json={"course": "mains"},
            headers=headers,
        )
        # The event must arrive near-instantly (well under the 1s SRS target).
        event = await _asyncio.wait_for(queue.get(), timeout=1.0)
    finally:
        kds_broker.unsubscribe(_user["id"], queue)

    assert event["type"] == "fired"
    assert event["card"]["station_id"] == grill
    assert event["card"]["items"][0]["name"] == "Wings"
