"""Issue #210 (M3·POS) — reopen a closed shift with an audit trail.

The shift lifecycle stopped at open → close: a shift closed in error (wrong
closing-cash count, premature close, a late refund) could never be reopened, so
the cashier had to live with a wrong Z-report or open a brand-new shift. This
slice adds ``POST /production/shifts/{id}/reopen``:

* a *closed* shift flips back to *open* and becomes the current open shift, with
  its reconciliation fields cleared so a fresh close recomputes them;
* the reopen is recorded in the tamper-evident audit trail (action
  ``shift.reopened``) so the correction is never silent;
* only a closed shift can be reopened, never while another shift is open, and
  the shift is owner-scoped (a foreign/unknown id is a 404).
"""
from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.audit_logs import Audit_logs
from sqlalchemy import select


async def _open_shift(client, headers, opening_cash=100.0):
    resp = await client.post(
        "/api/v1/production/shifts/open",
        json={"opening_cash": opening_cash},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _close_shift(client, headers, closing_cash=100.0):
    resp = await client.post(
        "/api/v1/production/shifts/close",
        json={"closing_cash": closing_cash},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _reopen(client, headers, shift_id, reason="Miscounted the drawer"):
    return await client.post(
        f"/api/v1/production/shifts/{shift_id}/reopen",
        json={"reason": reason},
        headers=headers,
    )


async def test_closed_shift_reopens_and_records_audit_trail(client):
    """Open → close → reopen. The shift is open again and is the current shift;
    its close-time reconciliation fields are cleared; an audit row records it."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    opened = await _open_shift(client, headers, opening_cash=100.0)
    shift_id = opened["id"]
    await _close_shift(client, headers, closing_cash=100.0)

    resp = await _reopen(client, headers, shift_id, reason="Miscounted the drawer")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == shift_id
    assert body["status"] == "open"
    # Reopening for a correction clears the prior close result.
    assert body["closing_cash"] is None
    assert body["end_time"] is None

    # It is once again the current open shift.
    current = (await client.get("/api/v1/production/shifts/current", headers=headers)).json()
    assert current["status"] == "open"
    assert current["shift"]["id"] == shift_id

    # The reopen is in the tamper-evident audit trail.
    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Audit_logs).where(Audit_logs.action == "shift.reopened")
            )
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].entity_type == "shift"
    assert rows[0].entity_id == str(shift_id)
    assert "Miscounted the drawer" in (rows[0].details or "")


async def test_cannot_reopen_a_shift_that_is_not_closed(client):
    """An open (not yet closed) shift cannot be reopened — there is nothing to
    reopen and it would be a no-op masking a bug."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    opened = await _open_shift(client, headers)

    resp = await _reopen(client, headers, opened["id"])
    assert resp.status_code == 400
    assert "closed" in resp.json()["detail"].lower()


async def test_cannot_reopen_while_another_shift_is_open(client):
    """Reopening must not break the single-open-drawer invariant: with a fresh
    shift already open, the earlier closed shift cannot be reopened."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    first = await _open_shift(client, headers)
    await _close_shift(client, headers)
    # A second shift is opened (and left open).
    await _open_shift(client, headers)

    resp = await _reopen(client, headers, first["id"])
    assert resp.status_code == 400
    assert "already open" in resp.json()["detail"].lower()


async def test_reopen_is_owner_scoped(client):
    """A merchant cannot reopen another merchant's shift, and an unknown id is a
    404 (the lookup is filtered on the owner)."""
    user_a, token_a, _ = await make_client_account(client)
    headers_a = auth_headers(token_a)
    opened = await _open_shift(client, headers_a)
    await _close_shift(client, headers_a)

    user_b, token_b, _ = await make_client_account(client)
    headers_b = auth_headers(token_b)

    foreign = await _reopen(client, headers_b, opened["id"])
    assert foreign.status_code == 404

    unknown = await _reopen(client, headers_a, 999999)
    assert unknown.status_code == 404
