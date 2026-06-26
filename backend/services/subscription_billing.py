"""Merchant subscription charging via the AGENT's own Moyasar account (Rail 2, CL-04).

A white-label agent resells subscriptions to his merchants and collects that money
into **his own** Moyasar account — the platform only hosts the billing UI; the
revenue is the agent's, not ours (our revenue is the wholesale quota the agent buys
from us, see ``services.quota_billing``). So a merchant subscription charge is
routed through the owning agent's Moyasar secret key (stored encrypted on the agent
row) against the merchant's stored card-on-file token (PAN never reaches us —
PAY-09; the token is tokenized by moyasar.js and stored encrypted on the client).

The charge **fails closed**: if the agent has not connected a Moyasar account, or
the merchant has no card on file, a :class:`SubscriptionChargeError` is raised so
the caller returns 402 and the billing period is *not* advanced. There is no
silent "manual = free" path — that would let merchants run unbilled. The only
credential-free path is the deterministic sandbox gateway (when neither the agent
nor the platform has any Moyasar key, e.g. dev/CI), which still produces a real
approve/decline so the flow is demonstrable without onboarding (OPS-08).
"""
import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from core.config import settings

logger = logging.getLogger(__name__)


def apply_coupon(
    fee: float, coupon_type: Optional[str], coupon_value: Optional[float]
) -> float:
    """Return the net subscription fee after applying a coupon (ISSUE-054).

    ``coupon_type`` is ``'percentage'`` (``coupon_value`` is a percent off) or
    ``'fixed'`` (a flat amount off in the fee currency). With no coupon — either
    field missing/zero — the fee is returned unchanged. The result is clamped at
    0 so a fixed coupon larger than the fee never produces a negative charge, and
    rounded to 2 decimals to match the recorded payment amount.
    """
    gross = float(fee or 0)
    if not coupon_type or not coupon_value:
        return round(gross, 2)
    if coupon_type == "percentage":
        net = gross * (1 - float(coupon_value) / 100.0)
    elif coupon_type == "fixed":
        net = gross - float(coupon_value)
    else:
        net = gross
    return round(max(net, 0.0), 2)


def compute_proration(
    old_fee: float, new_fee: float, days_remaining: int, cycle_days: int
) -> float:
    """Pro-rated charge (positive) or credit (negative) for a mid-cycle plan change
    (ISSUE-053).

    When the subscription fee changes partway through an already-paid billing
    period, only the unused remainder of the period is re-priced: the difference
    ``new_fee - old_fee`` is scaled by the fraction of the cycle still remaining
    (``days_remaining / cycle_days``). An upgrade yields a charge, a downgrade a
    credit. The fraction is clamped to ``[0, 1]`` so a stale/over-long remaining
    count never bills more than a whole cycle and an elapsed period bills nothing.
    Rounded to 2 decimals to match the recorded payment amount.
    """
    if cycle_days <= 0:
        return 0.0
    fraction = max(0.0, min(1.0, float(days_remaining) / float(cycle_days)))
    return round((float(new_fee) - float(old_fee)) * fraction, 2)


def is_in_trial(trial_end: Optional[str], today: date) -> bool:
    """True when a trial is configured and has not yet ended (ISSUE-054).

    ``trial_end`` is an ISO date string; the subscription is in trial — and the
    first charge deferred — until that date (exclusive: on/after ``trial_end``
    the charge is due). No trial date, or an unparseable one, means not in trial.
    """
    if not trial_end:
        return False
    try:
        return today < date.fromisoformat(trial_end)
    except ValueError:
        return False


class SubscriptionChargeError(Exception):
    """A Moyasar subscription charge was attempted and declined/failed."""


@dataclass
class ChargeResult:
    charged: bool  # True only when money actually moved through a gateway
    status: str  # "paid"
    method: str  # "moyasar" | "sandbox"
    reference: Optional[str]  # Moyasar payment id when charged


def _platform_moyasar_key() -> str:
    return (getattr(settings, "moyasar_api_key", "") or "").strip()


async def charge_subscription(
    *,
    amount: float,
    currency: str = "SAR",
    agent_moyasar_key: Optional[str] = None,
    card_token: Optional[str] = None,
    client_id: int,
    idempotency_key: Optional[str] = None,
) -> ChargeResult:
    """Charge a merchant subscription through the agent's Moyasar account (Rail 2).

    ``agent_moyasar_key`` is the owning agent's **decrypted** Moyasar secret key;
    ``card_token`` is the merchant's stored reusable card token. Fails closed: with
    no agent key AND no platform fallback key, or no card token, a
    :class:`SubscriptionChargeError` is raised (→ 402, period not advanced) rather
    than a silent free pass. With no key configured anywhere, the deterministic
    sandbox gateway runs so the flow stays demonstrable on un-onboarded installs.
    """
    from services.payment_gateway import (
        GatewayNotConfigured,
        PaymentDeclined,
        SandboxGateway,
        recurring_gateway,
    )

    key = (agent_moyasar_key or "").strip() or _platform_moyasar_key()
    gateway = recurring_gateway(key)

    # Live (real money) requires a card on file; the sandbox synthesizes its own.
    if not isinstance(gateway, SandboxGateway) and not card_token:
        raise SubscriptionChargeError("No card on file for this subscription")

    try:
        result = await gateway.charge(
            amount=amount,
            tender_type="card",
            currency=currency,
            token=card_token,
            metadata={
                "recurring": True,
                "description": f"Subscription (client {client_id})",
                "client_id": str(client_id),
                "idempotency_key": idempotency_key,
            },
        )
    except PaymentDeclined as exc:
        raise SubscriptionChargeError(f"Card declined: {exc.reason}") from exc
    except GatewayNotConfigured as exc:
        raise SubscriptionChargeError(str(exc)) from exc

    if not result.approved:
        raise SubscriptionChargeError(f"Card declined: {result.decline_reason or 'declined'}")

    return ChargeResult(
        charged=True, status="paid", method=result.gateway, reference=result.gateway_ref
    )


async def existing_settled_payment(db, *, client_id: int, period_key: str):
    """Return the merchant subscription payment already settled for this billing
    period (its ``period_key``), or None (FIN-04).

    A settled recurring charge stamps ``period_key`` with the period start. The pay
    endpoint and the dunning sweep consult this BEFORE charging so a double-click or
    a scheduler-vs-manual race for the same period reconciles to the first payment
    instead of charging the card again.
    """
    from sqlalchemy import select

    from models.subscription_payments import Subscription_payments

    return (
        await db.execute(
            select(Subscription_payments).where(
                Subscription_payments.client_id == client_id,
                Subscription_payments.period_key == period_key,
            )
        )
    ).scalars().first()


async def record_settled_payment(
    db,
    *,
    merchant,
    payer_user_id: str,
    charge: "ChargeResult",
    cycle: str,
    period_start: str,
    period_end: str,
    agent_row=None,
    amount: Optional[float] = None,
):
    """Persist a settled merchant subscription payment, advance the billing period,
    and clear any dunning state (status -> active).

    ``amount`` is the actual amount collected this period; when omitted it falls
    back to the merchant's full ``subscription_fee``. A subscription coupon
    (ISSUE-054) passes the discounted net here so the recorded payment reflects
    what the client was charged. This payment is entirely the agent's revenue —
    the platform takes no cut here (our revenue is the wholesale quota the agent
    buys, ``agent_quota_payments``); there is no commission split.

    Shared by the interactive pay endpoint (CL-04) and the dunning sweep (CL-06)
    so a successful retry records the payment exactly like a manual pay. ``agent_row``
    is accepted for call-site symmetry but is not needed here. Runs in the caller's
    transaction (no commit). Returns the persisted payment row.
    """
    # Local imports keep this module importable without the full model graph and
    # avoid a circular import with the tenant router.
    from sqlalchemy import update
    from sqlalchemy.exc import IntegrityError

    from models.clients import Clients
    from models.subscription_payments import Subscription_payments

    collected = float(merchant.subscription_fee or 0) if amount is None else float(amount)
    payment = Subscription_payments(
        user_id=str(payer_user_id),
        client_id=merchant.id,
        amount=collected,
        billing_cycle=cycle,
        period_start=period_start,
        # FIN-04: stamp the settled-period idempotency key so a second settlement of
        # the same period conflicts on uq_subscription_payment_client_period.
        period_key=period_start,
        period_end=period_end,
        method=charge.method,
        reference=charge.reference,
    )
    db.add(payment)
    try:
        # Savepoint so a period-conflict (a concurrent settlement that raced past
        # the caller's pre-check) doesn't poison the caller's transaction (FIN-04).
        async with db.begin_nested():
            await db.flush()  # assign the payment id
    except IntegrityError:
        existing = await existing_settled_payment(
            db, client_id=merchant.id, period_key=period_start
        )
        if existing is not None:
            # The period was already settled — reconcile to it; the account is
            # already recovered/advanced by the winning settlement.
            return existing
        raise

    # Recover the subscription: active again, billing advanced, dunning cleared.
    await db.execute(
        update(Clients)
        .where(Clients.id == merchant.id)
        .values(
            subscription_status="active",
            next_billing_date=period_end,
            dunning_attempts=0,
            grace_deadline=None,
            is_active=True,
        )
    )
    return payment
