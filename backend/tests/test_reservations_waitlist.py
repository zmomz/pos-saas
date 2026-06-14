"""ISSUE-069 — Reservations + waitlist for the restaurant vertical (RST).

A restaurant can book a table ahead (a *reservation* for a table + time that
surfaces on the floor) and queue walk-ins (a *waitlist* that can be seated to a
table, opening an order ticket and occupying the table). Both surfaces sit
behind the same double-gate as the rest of ``/api/v1/restaurant`` (business_type
∈ restaurant/both + the ``restaurant`` feature) and are owner-scoped (SEC-02).
"""
from conftest import auth_headers, make_client_account


async def _make_table(client, token, name="T1", seats=4):
    resp = await client.post(
        "/api/v1/restaurant/tables",
        json={"name": name, "seats": seats},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# AC1 — a reservation can be created for a table/time.
# ---------------------------------------------------------------------------
async def test_create_reservation_for_table_and_time(client):
    _user, token, _cid = await make_client_account(client, business_type="restaurant")
    table_id = await _make_table(client, token)

    resp = await client.post(
        "/api/v1/restaurant/reservations",
        json={
            "table_id": table_id,
            "reserved_at": "2026-12-31T19:30:00",
            "customer_name": "Al-Otaibi",
            "party_size": 4,
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["table_id"] == table_id
    assert body["customer_name"] == "Al-Otaibi"
    assert body["party_size"] == 4
    assert body["status"] == "booked"
    assert body["reserved_at"].startswith("2026-12-31T19:30")


async def test_reservation_surfaces_on_the_floor(client):
    """AC1 — a booked reservation shows up on its table's floor tile."""
    _user, token, _cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    table_id = await _make_table(client, token, name="Patio-1")

    # A table with no booking carries no reservation overlay.
    before = (await client.get("/api/v1/restaurant/tables", headers=headers)).json()["items"][0]
    assert before["next_reservation"] is None

    await client.post(
        "/api/v1/restaurant/reservations",
        json={"table_id": table_id, "reserved_at": "2026-12-31T20:00:00", "party_size": 2},
        headers=headers,
    )

    after = (await client.get("/api/v1/restaurant/tables", headers=headers)).json()["items"][0]
    assert after["next_reservation"] is not None
    assert after["next_reservation"]["table_id"] == table_id
    assert after["next_reservation"]["status"] == "booked"


async def test_reservations_are_owner_scoped(client):
    """SEC-02 — one client can never see another's reservations."""
    _u1, token1, _c1 = await make_client_account(client, business_type="restaurant")
    _u2, token2, _c2 = await make_client_account(client, business_type="restaurant")
    table_id = await _make_table(client, token1)

    await client.post(
        "/api/v1/restaurant/reservations",
        json={"table_id": table_id, "reserved_at": "2026-12-31T19:30:00"},
        headers=auth_headers(token1),
    )

    mine = await client.get("/api/v1/restaurant/reservations", headers=auth_headers(token1))
    assert mine.json()["total"] == 1
    theirs = await client.get("/api/v1/restaurant/reservations", headers=auth_headers(token2))
    assert theirs.json()["items"] == []


async def test_retail_client_is_blocked_from_reservations(client):
    _user, token, _cid = await make_client_account(client, business_type="retail")
    resp = await client.get("/api/v1/restaurant/reservations", headers=auth_headers(token))
    assert resp.status_code == 403, resp.text
    resp2 = await client.get("/api/v1/restaurant/waitlist", headers=auth_headers(token))
    assert resp2.status_code == 403, resp2.text


async def test_cancel_reservation_removes_it_from_the_floor(client):
    """A cancelled booking no longer overlays its table tile."""
    _user, token, _cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    table_id = await _make_table(client, token)

    rid = (
        await client.post(
            "/api/v1/restaurant/reservations",
            json={"table_id": table_id, "reserved_at": "2026-12-31T19:30:00"},
            headers=headers,
        )
    ).json()["id"]

    cancelled = await client.delete(f"/api/v1/restaurant/reservations/{rid}", headers=headers)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"

    tile = (await client.get("/api/v1/restaurant/tables", headers=headers)).json()["items"][0]
    assert tile["next_reservation"] is None


async def test_reservation_for_foreign_table_is_rejected(client):
    """SEC-02 — can't book onto another client's table."""
    _u1, token1, _c1 = await make_client_account(client, business_type="restaurant")
    _u2, token2, _c2 = await make_client_account(client, business_type="restaurant")
    foreign_table = await _make_table(client, token1)

    resp = await client.post(
        "/api/v1/restaurant/reservations",
        json={"table_id": foreign_table, "reserved_at": "2026-12-31T19:30:00"},
        headers=auth_headers(token2),
    )
    assert resp.status_code == 400, resp.text


# ---------------------------------------------------------------------------
# AC2 — a waitlist queues parties and can seat them to a table.
# ---------------------------------------------------------------------------
async def test_waitlist_queues_parties_in_arrival_order(client):
    _user, token, _cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)

    for name in ("First", "Second", "Third"):
        resp = await client.post(
            "/api/v1/restaurant/waitlist",
            json={"customer_name": name, "party_size": 2},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["status"] == "waiting"

    queue = await client.get("/api/v1/restaurant/waitlist", headers=headers)
    names = [e["customer_name"] for e in queue.json()["items"]]
    assert names == ["First", "Second", "Third"]


async def test_seat_waitlist_party_opens_ticket_and_occupies_table(client):
    _user, token, _cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    table_id = await _make_table(client, token, name="Window-2")

    entry_id = (
        await client.post(
            "/api/v1/restaurant/waitlist",
            json={"customer_name": "Walk-in", "party_size": 3},
            headers=headers,
        )
    ).json()["id"]

    seated = await client.post(
        f"/api/v1/restaurant/waitlist/{entry_id}/seat",
        json={"table_id": table_id},
        headers=headers,
    )
    assert seated.status_code == 200, seated.text
    body = seated.json()
    assert body["entry"]["status"] == "seated"
    assert body["entry"]["seated_table_id"] == table_id
    assert body["ticket"]["table_id"] == table_id
    assert body["ticket"]["status"] == "open"

    # The table is now occupied and linked to the new ticket.
    tile = (await client.get(f"/api/v1/restaurant/tables/{table_id}", headers=headers)).json()
    assert tile["state"] == "occupied"
    assert tile["current_ticket_id"] == body["ticket"]["id"]

    # The seated party has left the live (waiting) queue.
    queue = await client.get("/api/v1/restaurant/waitlist", headers=headers)
    assert queue.json()["items"] == []


async def test_cannot_seat_party_onto_occupied_table(client):
    _user, token, _cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    table_id = await _make_table(client, token)

    e1 = (
        await client.post(
            "/api/v1/restaurant/waitlist", json={"customer_name": "A"}, headers=headers
        )
    ).json()["id"]
    e2 = (
        await client.post(
            "/api/v1/restaurant/waitlist", json={"customer_name": "B"}, headers=headers
        )
    ).json()["id"]

    first = await client.post(
        f"/api/v1/restaurant/waitlist/{e1}/seat", json={"table_id": table_id}, headers=headers
    )
    assert first.status_code == 200, first.text

    # The table is occupied — seating a second party onto it is rejected.
    second = await client.post(
        f"/api/v1/restaurant/waitlist/{e2}/seat", json={"table_id": table_id}, headers=headers
    )
    assert second.status_code == 409, second.text


async def test_waitlist_is_owner_scoped(client):
    _u1, token1, _c1 = await make_client_account(client, business_type="restaurant")
    _u2, token2, _c2 = await make_client_account(client, business_type="restaurant")

    await client.post(
        "/api/v1/restaurant/waitlist", json={"customer_name": "OwnerOnly"}, headers=auth_headers(token1)
    )
    other = await client.get("/api/v1/restaurant/waitlist", headers=auth_headers(token2))
    assert other.json()["items"] == []
