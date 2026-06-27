"""Single-use, short-lived tickets for authenticating EventSource (SSE) streams.

The browser ``EventSource`` API can't set an Authorization header, so the KDS
live feed (routers/restaurant.py::kds_stream) historically carried the long-lived
bearer JWT in the query string — which leaks into server/proxy access logs and
browser history (FE-02). Instead the SPA first POSTs (authenticated, header
bearer) to mint a *stream ticket*: an opaque, CSPRNG-random, single-use token
with a short TTL. The ticket rides the SSE URL; the stream validates and *burns*
it on connect, so a leaked URL is useless — an already-used or expired ticket is
rejected.

State is in-process (a plain dict), matching the KDS broker's in-process design
(services/kds_channel.py; see #166 for the shared-state follow-up): an SSE
connection must reach the same worker as its broker anyway, so a ticket consumed
in that same process is the right scope for this slice.
"""
import secrets
import time
from dataclasses import dataclass

# Tickets are minted immediately before the EventSource connects, so the window
# only needs to cover that round-trip (plus clock slack). Short by design: a
# leaked URL is useless within seconds even before it is burned.
STREAM_TICKET_TTL_SECONDS = 30


@dataclass
class _Ticket:
    user_id: str
    expires_at: float


# ticket -> _Ticket. Single process; see module docstring.
_tickets: dict[str, _Ticket] = {}


def _now(now: float | None) -> float:
    # Monotonic so wall-clock adjustments can't extend/shorten a ticket; tests
    # inject ``now`` to exercise the expiry boundary deterministically.
    return time.monotonic() if now is None else now


def _purge_expired(now: float) -> None:
    for key in [k for k, v in _tickets.items() if v.expires_at < now]:
        del _tickets[key]


def issue_stream_ticket(
    user_id: str,
    *,
    ttl: float = STREAM_TICKET_TTL_SECONDS,
    now: float | None = None,
) -> str:
    """Mint and store a single-use ticket bound to ``user_id``; return it."""
    clock = _now(now)
    _purge_expired(clock)
    ticket = secrets.token_urlsafe(32)
    _tickets[ticket] = _Ticket(user_id=str(user_id), expires_at=clock + ttl)
    return ticket


def consume_stream_ticket(ticket: str, *, now: float | None = None) -> str | None:
    """Validate and *burn* ``ticket``; return its subject, or None if it is
    unknown, already used, or expired."""
    entry = _tickets.pop(ticket, None)  # pop => single-use burn
    if entry is None:
        return None
    if entry.expires_at < _now(now):
        return None
    return entry.user_id
