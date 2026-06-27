"""FE-02 — Replace the SSE token-in-URL with a short-lived, single-use ticket.

The KDS live feed rides the browser ``EventSource`` API, which can't set an
Authorization header, so the bearer JWT used to travel in the stream URL's query
string — where it leaks to access logs and browser history. Instead the SPA now
mints an opaque, CSPRNG-random, single-use *stream ticket* via an authenticated
POST; the SSE URL carries the ticket; the stream validates and **burns** it on
connect.

One behavior per test, through the public interfaces:
  * the ticket service (issue / consume / single-use / expiry);
  * the authenticated mint endpoint (auth + restaurant double-gate);
  * the SSE stream endpoint (ticket required, used/expired rejected, valid works).
"""
import pytest

from conftest import auth_headers, make_client_account
from services import stream_ticket


# ---------------------------------------------------------------------------
# Ticket service (the chokepoint the endpoints route through)
# ---------------------------------------------------------------------------
def test_issued_ticket_consumes_to_its_subject():
    ticket = stream_ticket.issue_stream_ticket("user-42")
    assert ticket and isinstance(ticket, str)
    assert stream_ticket.consume_stream_ticket(ticket) == "user-42"


def test_ticket_is_single_use():
    """A ticket is burned on first consume; a replay (leaked URL) is rejected."""
    ticket = stream_ticket.issue_stream_ticket("user-1")
    assert stream_ticket.consume_stream_ticket(ticket) == "user-1"
    assert stream_ticket.consume_stream_ticket(ticket) is None


def test_expired_ticket_is_rejected():
    now = 1000.0
    # Inside the TTL window: valid.
    ticket = stream_ticket.issue_stream_ticket("user-1", ttl=30, now=now)
    assert stream_ticket.consume_stream_ticket(ticket, now=now + 29) == "user-1"
    # Past the TTL window: rejected.
    ticket2 = stream_ticket.issue_stream_ticket("user-1", ttl=30, now=now)
    assert stream_ticket.consume_stream_ticket(ticket2, now=now + 31) is None


def test_unknown_ticket_is_rejected():
    assert stream_ticket.consume_stream_ticket("never-issued") is None


# ---------------------------------------------------------------------------
# Mint endpoint — authenticated + behind the restaurant double-gate
# ---------------------------------------------------------------------------
async def test_mint_requires_authentication(client):
    resp = await client.post("/api/v1/restaurant/kds/stream-ticket")
    assert resp.status_code == 401, resp.text


async def test_mint_is_restaurant_gated(client):
    """A retail merchant can't mint a KDS stream ticket (double-gate, 403)."""
    _user, token, _cid = await make_client_account(client, business_type="retail")
    resp = await client.post(
        "/api/v1/restaurant/kds/stream-ticket", headers=auth_headers(token)
    )
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# Stream endpoint — ticket required; the old token-in-URL path is gone
# ---------------------------------------------------------------------------
async def test_stream_rejects_a_bad_ticket(client):
    resp = await client.get("/api/v1/restaurant/kds/stream?ticket=not-a-real-ticket")
    assert resp.status_code == 401, resp.text


async def test_stream_no_longer_accepts_a_bearer_jwt_in_the_url(client):
    """A long-lived JWT in the URL must not authenticate the stream (FE-02)."""
    _user, token, _cid = await make_client_account(client, business_type="restaurant")
    resp = await client.get(f"/api/v1/restaurant/kds/stream?token={token}")
    # The token param is no longer read: the now-required ticket is missing (422)
    # and even if treated as a ticket it isn't one (401) — never a 200 stream.
    assert resp.status_code in (401, 422), resp.text


async def test_mint_binds_an_opaque_single_use_ticket(client):
    """The mint endpoint stores a ticket that resolves to the authenticated
    subject and is single-use — so the SSE stream (which consumes it on connect)
    authenticates the right tenant and a replayed/leaked URL is rejected.

    We assert the burn against the ticket service directly rather than reading the
    live HTTP stream: the SSE response is an endless generator that the in-memory
    ASGI transport buffers (see test_phase5_rst_kds_kot.py), so the test shares the
    app's in-process ticket store and exercises the same consume the stream runs.
    """
    user, token, _cid = await make_client_account(client, business_type="restaurant")
    mint = await client.post(
        "/api/v1/restaurant/kds/stream-ticket", headers=auth_headers(token)
    )
    assert mint.status_code == 200, mint.text
    ticket = mint.json()["ticket"]
    assert ticket and token not in ticket  # opaque, not the bearer JWT

    # Resolves to the authenticated subject (the stream's gate keys on this)...
    assert stream_ticket.consume_stream_ticket(ticket) == user["id"]
    # ...and is single-use: a replayed/leaked URL is rejected.
    assert stream_ticket.consume_stream_ticket(ticket) is None
