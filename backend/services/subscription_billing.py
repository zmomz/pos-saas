"""Subscription charging via the agent's Stripe Connect gateway (Phase 5 CL-04).

When ``STRIPE_SECRET_KEY`` is configured, a client's subscription payment is
charged through Stripe. If the owning agent has a connected account
(``agents.stripe_account_id``), the charge is routed to that account (Stripe
Connect, ``stripe_account`` request option) so the white-label reseller collects
the fee directly.

When Stripe is **not** configured the function fails open to a ``manual`` settled
record — preserving the pre-Stripe behaviour so dev/CI and self-hosted installs
without a gateway keep working. A genuine card decline (Stripe configured) raises
:class:`SubscriptionChargeError` so the caller can return 402 and *not* advance
the billing period.
"""
import logging
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
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
    """A configured Stripe charge was attempted and declined/failed."""


@dataclass
class ChargeResult:
    charged: bool  # True only when money actually moved through Stripe
    status: str  # "paid" | "manual"
    method: str  # "stripe" | "manual"
    reference: Optional[str]  # Stripe PaymentIntent id when charged


def _stripe_configured() -> bool:
    return bool(getattr(settings, "stripe_secret_key", None))


async def charge_subscription(
    *,
    amount: float,
    currency: str = "sar",
    agent_stripe_account: Optional[str] = None,
    client_id: int,
    idempotency_key: Optional[str] = None,
) -> ChargeResult:
    """Charge a subscription fee. See module docstring for the gating semantics."""
    if not _stripe_configured():
        logger.info("Stripe not configured; recording manual subscription payment.")
        return ChargeResult(charged=False, status="manual", method="manual", reference=None)

    import stripe

    from services.payment import initialize_stripe

    if not stripe.api_key:
        await initialize_stripe()

    amount_cents = int((Decimal(str(amount)) * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    request_options = {}
    if idempotency_key:
        request_options["idempotency_key"] = idempotency_key
    if agent_stripe_account:
        # Route the charge to the agent's connected account (Stripe Connect).
        request_options["stripe_account"] = agent_stripe_account

    try:
        intent = await stripe.PaymentIntent.create_async(
            amount=amount_cents,
            currency=currency,
            confirm=True,
            automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
            metadata={"client_id": str(client_id), "kind": "subscription"},
            **request_options,
        )
    except stripe.error.CardError as exc:
        raise SubscriptionChargeError(f"Card declined: {exc}") from exc
    except stripe.error.StripeError as exc:
        raise SubscriptionChargeError(f"Stripe charge failed: {exc}") from exc

    if getattr(intent, "status", None) != "succeeded":
        raise SubscriptionChargeError(f"Charge not completed (status={getattr(intent, 'status', '?')})")

    return ChargeResult(charged=True, status="paid", method="stripe", reference=intent.id)


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
    """Persist a settled subscription payment + a balanced commission row, advance
    the billing period, and clear any dunning state (status -> active).

    ``amount`` is the actual amount collected this period; when omitted it falls
    back to the merchant's full ``subscription_fee``. A subscription coupon
    (ISSUE-054) passes the discounted net here so the recorded payment and the
    commission split's gross both reflect what the client was charged.

    Shared by the interactive pay endpoint (CL-04) and the dunning sweep (CL-06)
    so a successful retry records the payment exactly like a manual pay. Runs in
    the caller's transaction (no commit). Returns the persisted payment row.
    """
    # Local imports keep this module importable without the full model graph and
    # avoid a circular import with the tenant router.
    from sqlalchemy import select, update

    from models.clients import Clients
    from models.commission_ledger import Commission_ledger
    from models.packages import Packages
    from models.subscription_payments import Subscription_payments
    from services.commission import compute_commission_split

    collected = float(merchant.subscription_fee or 0) if amount is None else float(amount)
    payment = Subscription_payments(
        user_id=str(payer_user_id),
        client_id=merchant.id,
        amount=collected,
        billing_cycle=cycle,
        period_start=period_start,
        period_end=period_end,
        method=charge.method,
        reference=charge.reference,
    )
    db.add(payment)
    # Flush so the payment gets its id; the commission row references it 1:1.
    await db.flush()

    # RSL-01: decompose the gross fee into the platform master's cut (per-client
    # amortized package wholesale) and the agent's net margin, written atomically
    # with the payment. An unresolvable package degrades to master_cut=0 (whole
    # fee to the agent) — still balanced, never blocking.
    package = None
    if agent_row is not None and getattr(agent_row, "package_type", None) is not None:
        package = (
            await db.execute(select(Packages).where(Packages.id == agent_row.package_type))
        ).scalar_one_or_none()
    fee = collected
    master_cut, agent_net = compute_commission_split(
        gross=fee,
        wholesale_price=float(getattr(package, "wholesale_price", 0) or 0),
        client_slots=int(getattr(package, "client_slots", 0) or 0),
    )
    db.add(
        Commission_ledger(
            user_id=(agent_row.user_id if agent_row is not None else str(payer_user_id)),
            agent_id=merchant.agent_id,
            client_id=merchant.id,
            subscription_payment_id=payment.id,
            package_id=(package.id if package is not None else None),
            gross=round(fee, 2),
            master_cut=master_cut,
            agent_net=agent_net,
            billing_cycle=cycle,
            period_start=period_start,
            period_end=period_end,
        )
    )

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
