"""Issue #210 (M3·POS) — end-of-day checklist that gates the shift close.

Reopening a closed shift (the first #210 slice) fixed corrections *after* the
fact. This slice stops the most common reason a close is wrong in the first
place: closing the drawer while operational work is still parked. A held
(parked) ticket (POS-10) is an unfinished sale — money the cashier still owes
the till. Closing over it silently strands it.

``GET /production/shifts/eod-checklist`` surfaces the close-readiness checklist
for the current open shift, and ``POST /production/shifts/close`` now *gates* on
its blocking items:

* with held tickets outstanding the checklist is not ready and the close is
  refused (400) — the cashier must recall/settle them first;
* a manager can still force the close with ``override`` + a reason, which is
  recorded in the tamper-evident audit trail (``shift.close_overridden``) so the
  bypass is never silent;
* with nothing parked the checklist is ready and the close behaves exactly as
  before (regression guard).
"""
import uuid

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.audit_logs import Audit_logs
from models.transactions import Transactions
from sqlalchemy import select


async def _open_shift(client, headers, opening_cash=100.0):
    resp = await client.post(
        "/api/v1/production/shifts/open",
        json={"opening_cash": opening_cash},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _park_held_ticket(owner_id, client_id, total=42.0):
    """Insert a parked (``held``) ticket the way POS-10 hold does, so the EOD
    checklist sees an outstanding unfinished sale."""
    async with db_manager.async_session_maker() as db:
        held = Transactions(
            user_id=owner_id,
            client_id=client_id,
            invoice_number=f"HELD-{uuid.uuid4().hex[:8]}",
            total_amount=total,
            payment_method="held",
            status="held",
        )
        db.add(held)
        await db.commit()


async def _eod_checklist(client, headers):
    return await client.get("/api/v1/production/shifts/eod-checklist", headers=headers)


async def _close(client, headers, **extra):
    return await client.post(
        "/api/v1/production/shifts/close",
        json={"closing_cash": 100.0, **extra},
        headers=headers,
    )


async def test_eod_checklist_not_ready_when_held_orders_outstanding(client):
    """A parked ticket leaves the checklist not-ready and flags the blocking
    ``no_held_orders`` item with the outstanding count."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _open_shift(client, headers)
    await _park_held_ticket(user["id"], client_id)

    resp = await _eod_checklist(client, headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ready_to_close"] is False
    items = {i["key"]: i for i in body["items"]}
    held = items["no_held_orders"]
    assert held["blocking"] is True
    assert held["satisfied"] is False
    assert held["count"] == 1


async def test_eod_checklist_ready_when_nothing_parked(client):
    """With nothing parked every blocking item is satisfied and the shift is
    ready to close."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _open_shift(client, headers)

    resp = await _eod_checklist(client, headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ready_to_close"] is True
    assert all(i["satisfied"] for i in body["items"] if i["blocking"])


async def test_eod_checklist_requires_an_open_shift(client):
    """The checklist is for the current open drawer; with none open it is a 404."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    resp = await _eod_checklist(client, headers)
    assert resp.status_code == 404


async def test_close_is_refused_while_a_ticket_is_parked(client):
    """The checklist gates the close: a held ticket blocks it with a 400 that
    names the unfinished work."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _open_shift(client, headers)
    await _park_held_ticket(user["id"], client_id)

    resp = await _close(client, headers)
    assert resp.status_code == 400, resp.text
    assert "held" in resp.json()["detail"].lower()

    # The shift is still open — the refused close did not strand it half-closed.
    current = (await client.get("/api/v1/production/shifts/current", headers=headers)).json()
    assert current["status"] == "open"


async def test_close_override_forces_close_with_audit_trail(client):
    """A manager can force the close past the checklist with a reason; the
    bypass is recorded in the tamper-evident audit trail."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _open_shift(client, headers)
    await _park_held_ticket(user["id"], client_id)

    resp = await _close(
        client, headers, override=True, override_reason="End of day; ticket abandoned"
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "closed"

    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Audit_logs).where(Audit_logs.action == "shift.close_overridden")
            )
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].entity_type == "shift"
    assert "abandoned" in (rows[0].details or "")


async def test_close_override_requires_a_reason(client):
    """Forcing the close past the checklist demands a reason — an unexplained
    override is itself a silent edit."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _open_shift(client, headers)
    await _park_held_ticket(user["id"], client_id)

    resp = await _close(client, headers, override=True)
    assert resp.status_code == 400, resp.text
    assert "reason" in resp.json()["detail"].lower()


async def test_close_succeeds_normally_when_checklist_ready(client):
    """Regression: with nothing parked the close is unchanged — no override
    needed, balanced reconciliation returned."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _open_shift(client, headers, opening_cash=100.0)

    resp = await _close(client, headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "closed"
    assert body["reconciliation"] == "balanced"
