"""Issue #229 (M9·Analytics) — checkout conversion funnel.

The funnel slice of the advanced-analytics epic. Where CLV/repeat-rate answers
"who are our customers and what are they worth", cohorts answer "how well do we
keep them", and peak-hours answers "when do they buy", the funnel answers "of
every ticket we open, how many convert to a kept sale — and where do we lose
them?".

It walks a ticket through three ordered stages, each derived purely from the
transaction ``status`` composition in the window:

* **started**   — every ticket opened at the POS (a credit note is a refund
  *document*, not an opened ticket, so it is excluded);
* **completed** — tickets that became a finalised sale (``held`` = parked and
  ``voided`` = cancelled drop out here);
* **retained**  — sales whose revenue we kept (``refunded`` / ``partial_refunded``
  gave the money back, so they drop out here).

``biggest_dropoff`` names the transition that loses the most tickets — the raw
material for a "where are we leaking sales" callout. All figures are
tenant-scoped and aggregated server-side (one grouped-by-status query).
"""
from datetime import datetime, timedelta, timezone

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.transactions import Transactions


async def _seed(client_id, user_id, *, status="completed", total=10.0, idx=0):
    """One transaction with ``status`` a few days ago (inside any sane window)."""
    created = datetime.now(timezone.utc) - timedelta(days=2)
    async with db_manager.async_session_maker() as db:
        db.add(
            Transactions(
                user_id=user_id,
                client_id=client_id,
                invoice_number=f"INV-FN-{client_id}-{status}-{idx}",
                subtotal=total,
                vat_amount=0.0,
                discount_amount=0.0,
                total_amount=total,
                payment_method="cash",
                status=status,
                created_at=created,
            )
        )
        await db.commit()


def _stages(body):
    return {s["stage"]: s for s in body["stages"]}


async def test_funnel_counts_and_rates(client):
    """Stage counts and rates follow the status composition of the window."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # 4 plain completed + 1 legacy NULL-status (also a completed sale) = 5 completed.
    for i in range(4):
        await _seed(client_id, user["id"], status="completed", idx=i)
    await _seed(client_id, user["id"], status=None, idx=99)  # legacy completed
    await _seed(client_id, user["id"], status="held", idx=0)
    await _seed(client_id, user["id"], status="held", idx=1)
    await _seed(client_id, user["id"], status="voided", idx=0)
    await _seed(client_id, user["id"], status="refunded", idx=0)
    # A credit note is a refund document, not an opened ticket — excluded entirely.
    await _seed(client_id, user["id"], status="credit_note", idx=0)

    resp = await client.get("/api/v1/reports/sales-funnel?lookback=30", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["method"] == "checkout_funnel"
    assert body["lookback_days"] == 30
    # started = 5 completed + 2 held + 1 voided + 1 refunded = 9 (credit_note excluded)
    assert body["total_tickets"] == 9

    stages = _stages(body)
    assert [s["stage"] for s in body["stages"]] == ["started", "completed", "retained"]

    assert stages["started"]["count"] == 9
    assert stages["completed"]["count"] == 6  # 5 completed + 1 refunded (was paid)
    assert stages["retained"]["count"] == 5  # refunded gave the money back

    assert abs(stages["started"]["conversion_rate"] - 1.0) < 1e-6
    assert abs(stages["completed"]["conversion_rate"] - round(6 / 9, 4)) < 1e-6
    assert abs(stages["retained"]["conversion_rate"] - round(5 / 9, 4)) < 1e-6

    # step_rate: relative to the previous stage.
    assert abs(stages["started"]["step_rate"] - 1.0) < 1e-6
    assert abs(stages["completed"]["step_rate"] - round(6 / 9, 4)) < 1e-6
    assert abs(stages["retained"]["step_rate"] - round(5 / 6, 4)) < 1e-6


async def test_biggest_dropoff_is_the_largest_leak(client):
    """The dropoff callout names the transition that loses the most tickets."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # started=6 (3 completed + 2 held + 1 voided); completed=3; retained=3.
    for i in range(3):
        await _seed(client_id, user["id"], status="completed", idx=i)
    await _seed(client_id, user["id"], status="held", idx=0)
    await _seed(client_id, user["id"], status="held", idx=1)
    await _seed(client_id, user["id"], status="voided", idx=0)

    resp = await client.get("/api/v1/reports/sales-funnel?lookback=30", headers=headers)
    body = resp.json()

    drop = body["biggest_dropoff"]
    assert drop["from_stage"] == "started"
    assert drop["to_stage"] == "completed"
    assert drop["lost"] == 3  # 2 held + 1 voided
    assert abs(drop["rate"] - round(3 / 6, 4)) < 1e-6


async def test_empty_window_is_well_formed(client):
    """No tickets → zeroed stages and a null dropoff, still fully shaped."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    resp = await client.get("/api/v1/reports/sales-funnel?lookback=30", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total_tickets"] == 0
    assert body["biggest_dropoff"] is None
    stages = _stages(body)
    assert set(stages) == {"started", "completed", "retained"}
    for name in ("started", "completed", "retained"):
        assert stages[name]["count"] == 0
        assert stages[name]["conversion_rate"] == 0.0


async def test_funnel_is_tenant_scoped(client):
    """One tenant's tickets never leak into another tenant's funnel."""
    user_a, token_a, client_a = await make_client_account(client)
    user_b, token_b, client_b = await make_client_account(client)

    await _seed(client_b, user_b["id"], status="completed", idx=0)
    await _seed(client_b, user_b["id"], status="held", idx=0)

    resp = await client.get(
        "/api/v1/reports/sales-funnel?lookback=30", headers=auth_headers(token_a)
    )
    body = resp.json()
    assert body["total_tickets"] == 0
    assert body["biggest_dropoff"] is None


async def test_non_client_forbidden(client):
    """Only client accounts can read reports."""
    from conftest import make_agent_account

    _agent, token, _agent_id = await make_agent_account(client)
    resp = await client.get(
        "/api/v1/reports/sales-funnel?lookback=30", headers=auth_headers(token)
    )
    assert resp.status_code == 403
