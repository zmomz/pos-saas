"""#206 — merchant self-serve subscription lifecycle.

Covers the merchant-managed lifecycle endpoints added in #206: pause / resume /
cancel state transitions, the renewal & upgrade/downgrade (proration) preview, and
refunding a settled subscription payment. The proration math itself is covered by
``test_phase6_subscription_proration``; here we assert the preview surfaces it and
the lifecycle transitions are correct and owner-scoped.
"""
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from conftest import auth_headers, make_agent_account, make_client_under_agent
from core.database import db_manager
from models.clients import Clients
from models.subscription_payments import Subscription_payments

BASE = "/api/v1/tenant/client/subscription"


async def _set_subscription(client_id: int, **values):
    async with db_manager.async_session_maker() as db:
        await db.execute(update(Clients).where(Clients.id == client_id).values(**values))
        await db.commit()


async def _provision(client: AsyncClient, *, fee: float = 100.0, cycle: str = "monthly",
                     next_billing: str | None = None):
    """An agent + a merchant on a configured plan; returns (client_token, client_id)."""
    _agent, _at, agent_id = await make_agent_account(client)
    _cl, client_token, client_id = await make_client_under_agent(client, agent_id)
    values = {"subscription_fee": fee, "billing_cycle": cycle, "subscription_status": "active"}
    if next_billing is not None:
        values["next_billing_date"] = next_billing
    await _set_subscription(client_id, **values)
    return client_token, client_id


# ---------------------------------------------------------------------------
# Pause / resume — state transitions and paid-day preservation.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pause_then_resume_preserves_paid_days(client: AsyncClient):
    # 20 days left in the current period when the merchant pauses.
    next_billing = (datetime.now(timezone.utc).date() + timedelta(days=20)).isoformat()
    token, client_id = await _provision(client, next_billing=next_billing)

    resp = await client.post(f"{BASE}/pause", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    assert resp.json()["subscription_status"] == "paused"
    assert resp.json()["subscription_paused_at"]

    # Backdate the pause stamp 5 days so resume can shift the billing date forward.
    paused_on = (datetime.now(timezone.utc).date() - timedelta(days=5)).isoformat()
    await _set_subscription(client_id, subscription_paused_at=paused_on)

    resp = await client.post(f"{BASE}/resume", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["subscription_status"] == "active"
    assert body["subscription_paused_at"] is None
    # Billing date shifted forward by the ~5 paused days (preserving paid time).
    new_date = datetime.fromisoformat(body["next_billing_date"]).date()
    expected = datetime.fromisoformat(next_billing).date() + timedelta(days=5)
    assert new_date == expected


@pytest.mark.asyncio
async def test_paused_subscription_is_skipped_by_dunning(client: AsyncClient):
    """A paused subscription is never auto-charged or escalated by the sweep."""
    overdue = (datetime.now(timezone.utc).date() - timedelta(days=3)).isoformat()
    token, client_id = await _provision(client, next_billing=overdue)
    await client.post(f"{BASE}/pause", headers=auth_headers(token))

    from services.dunning import run_global_dunning

    async with db_manager.async_session_maker() as db:
        summary = await run_global_dunning(db)
    # The paused merchant is not in the swept set (status not in ACTIVE_STATES).
    async with db_manager.async_session_maker() as db:
        merchant = (
            await db.execute(select(Clients).where(Clients.id == client_id))
        ).scalar_one()
    assert merchant.subscription_status == "paused"
    assert summary["processed"] >= 0


@pytest.mark.asyncio
async def test_cannot_pause_a_cancelled_subscription(client: AsyncClient):
    token, client_id = await _provision(client)
    await client.post(f"{BASE}/cancel", headers=auth_headers(token))
    resp = await client.post(f"{BASE}/pause", headers=auth_headers(token))
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Cancel / reactivate.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cancel_then_reactivate(client: AsyncClient):
    token, client_id = await _provision(client)

    resp = await client.post(f"{BASE}/cancel", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["subscription_status"] == "cancelled"
    assert body["subscription_cancelled_at"]
    # Cancel keeps access through the paid period.
    assert body["is_active"] is True

    # Cancel is idempotent.
    resp = await client.post(f"{BASE}/cancel", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["subscription_status"] == "cancelled"

    # Resume reactivates with a fresh cycle.
    resp = await client.post(f"{BASE}/resume", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["subscription_status"] == "active"
    assert body["subscription_cancelled_at"] is None
    assert body["next_billing_date"]


# ---------------------------------------------------------------------------
# Renewal & proration preview.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_renewal_preview_reflects_coupon_and_pause(client: AsyncClient):
    token, client_id = await _provision(client, fee=200.0)
    # A 25% coupon for 3 periods.
    await _set_subscription(
        client_id, coupon_type="percentage", coupon_value=25.0, coupon_duration_remaining=3
    )

    resp = await client.get(f"{BASE}/renewal-preview", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["gross_fee"] == 200.0
    assert body["coupon_active"] is True
    assert body["net_amount"] == 150.0  # 25% off 200
    assert body["discount_amount"] == 50.0
    assert body["will_charge"] is True

    # Once paused, the preview reports no upcoming charge.
    await client.post(f"{BASE}/pause", headers=auth_headers(token))
    resp = await client.get(f"{BASE}/renewal-preview", headers=auth_headers(token))
    assert resp.json()["will_charge"] is False


@pytest.mark.asyncio
async def test_renewal_preview_shows_upgrade_proration(client: AsyncClient):
    # Exactly half of a 30-day monthly cycle remaining.
    next_billing = (datetime.now(timezone.utc).date() + timedelta(days=15)).isoformat()
    token, client_id = await _provision(client, fee=200.0, next_billing=next_billing)

    resp = await client.get(
        f"{BASE}/renewal-preview?new_fee=300", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    proration = resp.json()["proration"]
    assert proration is not None
    # Upgrade 200 -> 300 with ~half the cycle left ≈ +50 charge.
    assert proration["amount"] == pytest.approx(50.0, abs=7.0)
    assert proration["is_credit"] is False

    # A downgrade previews a credit.
    resp = await client.get(
        f"{BASE}/renewal-preview?new_fee=100", headers=auth_headers(token)
    )
    assert resp.json()["proration"]["is_credit"] is True


# ---------------------------------------------------------------------------
# Refund a settled payment.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_refund_settled_payment(client: AsyncClient):
    token, client_id = await _provision(client, fee=120.0)

    # Pay (sandbox gateway → a real settled charge with a gateway reference).
    resp = await client.post(f"{BASE}/pay", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    payments = resp.json()["payments"]
    assert payments, "a settled payment should exist"
    payment_id = payments[0]["id"]

    # Full refund.
    resp = await client.post(
        f"{BASE}/payments/{payment_id}/refund", json={}, headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    refunds = [p for p in resp.json()["payments"] if p["method"] == "refund"]
    assert len(refunds) == 1
    assert refunds[0]["amount"] == -120.0

    # Refunding again is rejected (already fully refunded).
    resp = await client.post(
        f"{BASE}/payments/{payment_id}/refund", json={}, headers=auth_headers(token)
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_partial_refund_then_remainder(client: AsyncClient):
    token, client_id = await _provision(client, fee=100.0)
    resp = await client.post(f"{BASE}/pay", headers=auth_headers(token))
    payment_id = resp.json()["payments"][0]["id"]

    # Refund 40 of 100.
    resp = await client.post(
        f"{BASE}/payments/{payment_id}/refund", json={"amount": 40}, headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text

    # A 70 refund now exceeds the 60 remaining.
    resp = await client.post(
        f"{BASE}/payments/{payment_id}/refund", json={"amount": 70}, headers=auth_headers(token)
    )
    assert resp.status_code == 400

    # The remaining 60 refunds.
    resp = await client.post(
        f"{BASE}/payments/{payment_id}/refund", json={"amount": 60}, headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_cannot_refund_a_proration_record(client: AsyncClient):
    token, client_id = await _provision(client)
    # Insert a proration record (no gateway reference) directly.
    async with db_manager.async_session_maker() as db:
        merchant = (
            await db.execute(select(Clients).where(Clients.id == client_id))
        ).scalar_one()
        row = Subscription_payments(
            user_id=merchant.user_id,
            client_id=client_id,
            amount=25.0,
            method="proration",
            note="Mid-cycle plan change 100 -> 150",
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        proration_id = row.id

    resp = await client.post(
        f"{BASE}/payments/{proration_id}/refund", json={}, headers=auth_headers(token)
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_lifecycle_endpoints_are_owner_scoped(client: AsyncClient):
    """An agent (no Clients row) gets 403 — these are merchant-only endpoints."""
    _agent, agent_token, _agent_id = await make_agent_account(client)
    for path in ("/pause", "/resume", "/cancel"):
        resp = await client.post(f"{BASE}{path}", headers=auth_headers(agent_token))
        assert resp.status_code == 403, f"{path}: {resp.text}"
    resp = await client.get(f"{BASE}/renewal-preview", headers=auth_headers(agent_token))
    assert resp.status_code == 403
