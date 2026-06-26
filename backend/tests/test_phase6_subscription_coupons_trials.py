"""Phase 6 — subscription coupons & trials (ISSUE-054, F-054 billing).

A subscription fee can carry a coupon (percentage / fixed, for a bounded number
of billing periods) and a trial that defers the first charge until the trial
ends. The pure ``apply_coupon`` / ``is_in_trial`` helpers are the testable core;
the agent set endpoint and the client pay endpoint wire them end-to-end.
"""
# ---------------------------------------------------------------------------
# Pure core: the coupon discount math.
# ---------------------------------------------------------------------------
def test_percentage_coupon_discounts_the_fee():
    from services.subscription_billing import apply_coupon

    # 25% off a 200.00 fee → 150.00 net.
    assert apply_coupon(200.0, "percentage", 25.0) == 150.0


def test_fixed_coupon_discounts_and_clamps_at_zero():
    from services.subscription_billing import apply_coupon

    # 30 off a 199 fee → 169.00 net.
    assert apply_coupon(199.0, "fixed", 30.0) == 169.0
    # A fixed coupon larger than the fee never produces a negative charge.
    assert apply_coupon(50.0, "fixed", 80.0) == 0.0
    # No coupon configured → fee unchanged.
    assert apply_coupon(199.0, None, None) == 199.0


def test_is_in_trial_only_while_trial_end_is_in_the_future():
    from datetime import date

    from services.subscription_billing import is_in_trial

    today = date(2026, 6, 14)
    # Trial ends in the future → still trialing (charge deferred).
    assert is_in_trial("2026-06-20", today) is True
    # Trial end has passed / is today → no longer trialing (charge now due).
    assert is_in_trial("2026-06-14", today) is False
    assert is_in_trial("2026-06-01", today) is False
    # No trial configured → never in trial.
    assert is_in_trial(None, today) is False


# ---------------------------------------------------------------------------
# End-to-end: agent sets a coupon → client's charges are discounted for the
# coupon's duration, then revert to the full fee (AC1).
# ---------------------------------------------------------------------------
import pytest  # noqa: E402
from httpx import AsyncClient  # noqa: E402

from conftest import (  # noqa: E402
    auth_headers,
    make_agent_account,
    make_client_under_agent,
)


def _latest_payment_amount(payload: dict) -> float:
    # payments are ordered newest-first by the subscription payload.
    return payload["payments"][0]["amount"]


async def _retire_current_period(client_id: int) -> None:
    """Simulate the next billing period arriving.

    FIN-04 enforces one settled charge per billing period (keyed on the period
    start), so paying twice on the same day is now correctly deduplicated. To
    exercise the coupon's multi-period duration in a single test run we retire the
    just-settled period by clearing its idempotency key, freeing today's slot for
    the next period's charge — what the ~30-day gap does in production.
    """
    from sqlalchemy import select

    from core.database import db_manager
    from models.subscription_payments import Subscription_payments

    async with db_manager.async_session_maker() as db:
        last = (
            await db.execute(
                select(Subscription_payments)
                .where(Subscription_payments.client_id == client_id)
                .order_by(Subscription_payments.id.desc())
            )
        ).scalars().first()
        last.period_key = f"retired-{last.id}"
        await db.commit()


@pytest.mark.asyncio
async def test_coupon_discounts_charges_for_its_duration_then_reverts(client: AsyncClient):
    _agent, agent_token, agent_id = await make_agent_account(client)
    _cl, client_token, client_id = await make_client_under_agent(client, agent_id)

    # Agent configures the fee and a 25%-off coupon good for 2 billing periods.
    resp = await client.put(
        f"/api/v1/tenant/agent/clients/{client_id}/subscription",
        headers=auth_headers(agent_token),
        json={
            "subscription_fee": 200.0,
            "billing_cycle": "monthly",
            "coupon_type": "percentage",
            "coupon_value": 25.0,
            "coupon_duration": 2,
        },
    )
    assert resp.status_code == 200, resp.text

    # First two charges are discounted (200 → 150); the third reverts to full.
    pay_url = "/api/v1/tenant/client/subscription/pay"
    first = await client.post(pay_url, headers=auth_headers(client_token))
    assert first.status_code == 200, first.text
    assert _latest_payment_amount(first.json()) == 150.0

    await _retire_current_period(client_id)
    second = await client.post(pay_url, headers=auth_headers(client_token))
    assert _latest_payment_amount(second.json()) == 150.0

    await _retire_current_period(client_id)
    third = await client.post(pay_url, headers=auth_headers(client_token))
    assert _latest_payment_amount(third.json()) == 200.0


# ---------------------------------------------------------------------------
# End-to-end: a trial defers the first charge until trial end (AC2).
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_trial_defers_first_charge_until_trial_ends(client: AsyncClient):
    _agent, agent_token, agent_id = await make_agent_account(client)
    _cl, client_token, client_id = await make_client_under_agent(client, agent_id)
    set_url = f"/api/v1/tenant/agent/clients/{client_id}/subscription"
    pay_url = "/api/v1/tenant/client/subscription/pay"

    # Agent starts the client on a trial that ends in the future.
    resp = await client.put(
        set_url,
        headers=auth_headers(agent_token),
        json={"subscription_fee": 200.0, "billing_cycle": "monthly", "trial_end": "2999-01-01"},
    )
    assert resp.status_code == 200, resp.text

    # Paying during the trial does NOT charge — the first charge is deferred.
    during = await client.post(pay_url, headers=auth_headers(client_token))
    assert during.status_code == 200, during.text
    body = during.json()
    assert body["payments"] == []
    assert body["subscription_status"] == "trialing"
    assert body["next_billing_date"] == "2999-01-01"

    # Once the trial has ended (date in the past), paying charges normally.
    ended = await client.put(
        set_url,
        headers=auth_headers(agent_token),
        json={"trial_end": "2000-01-01"},
    )
    assert ended.status_code == 200, ended.text
    after = await client.post(pay_url, headers=auth_headers(client_token))
    assert after.status_code == 200, after.text
    after_body = after.json()
    assert len(after_body["payments"]) == 1
    assert after_body["payments"][0]["amount"] == 200.0
    assert after_body["subscription_status"] == "active"
