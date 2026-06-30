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
from decimal import Decimal
from typing import Optional

from core.config import settings
from core.money import Number, quantize_money, to_decimal

logger = logging.getLogger(__name__)


def apply_coupon(
    fee: Number, coupon_type: Optional[str], coupon_value: Optional[Number]
) -> Decimal:
    """Return the net subscription fee after applying a coupon (ISSUE-054).

    ``coupon_type`` is ``'percentage'`` (``coupon_value`` is a percent off) or
    ``'fixed'`` (a flat amount off in the fee currency). With no coupon — either
    field missing/zero — the fee is returned unchanged. The result is clamped at
    0 so a fixed coupon larger than the fee never produces a negative charge, and
    quantized to 2 decimals to match the recorded payment amount.

    FIN-01/ISSUE-187: computed in exact Decimal and quantized half-up so a
    ``.xx5`` net (e.g. 73.25% off 10.00 = 2.675) charges 2.68, not the float
    half-even 2.67 that previously fed the gateway.
    """
    gross = to_decimal(fee or 0)
    if not coupon_type or not coupon_value:
        return quantize_money(gross)
    if coupon_type == "percentage":
        net = gross * (Decimal(1) - to_decimal(coupon_value) / Decimal(100))
    elif coupon_type == "fixed":
        net = gross - to_decimal(coupon_value)
    else:
        net = gross
    return quantize_money(max(net, Decimal(0)))


def compute_proration(
    old_fee: Number, new_fee: Number, days_remaining: int, cycle_days: int
) -> Decimal:
    """Pro-rated charge (positive) or credit (negative) for a mid-cycle plan change
    (ISSUE-053).

    When the subscription fee changes partway through an already-paid billing
    period, only the unused remainder of the period is re-priced: the difference
    ``new_fee - old_fee`` is scaled by the fraction of the cycle still remaining
    (``days_remaining / cycle_days``). An upgrade yields a charge, a downgrade a
    credit. The fraction is clamped to ``[0, 1]`` so a stale/over-long remaining
    count never bills more than a whole cycle and an elapsed period bills nothing.
    Quantized to 2 decimals (half-up) to match the recorded payment amount
    (FIN-01/ISSUE-187 — exact Decimal, no float drift on a ``.xx5`` boundary).
    """
    if cycle_days <= 0:
        return quantize_money(0)
    fraction = max(Decimal(0), min(Decimal(1), to_decimal(days_remaining) / to_decimal(cycle_days)))
    return quantize_money((to_decimal(new_fee) - to_decimal(old_fee)) * fraction)


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


# ISSUE-182: a settled charge is recorded by reserving the (client, period_key) row
# FIRST, then charging, then finalising it. While the gateway charge is in flight the
# row carries this sentinel method and a zero amount; finalise rewrites it to the real
# charge, and a decline/crash releases it. It is never a real payment, so rollups and
# payment history exclude it.
RESERVING_METHOD = "reserving"


class SubscriptionChargeError(Exception):
    """A Moyasar subscription charge was attempted and declined/failed."""


class SubscriptionRefundError(Exception):
    """A subscription-payment refund was attempted and declined/failed (#206)."""


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


@dataclass
class RefundResult:
    refunded: bool  # True only when the gateway accepted the refund
    method: str  # "moyasar" | "sandbox"
    reference: Optional[str]  # the refund's gateway reference


async def refund_subscription(
    *,
    gateway_ref: str,
    amount: float,
    agent_moyasar_key: Optional[str] = None,
) -> RefundResult:
    """Refund a settled merchant subscription payment through the agent's Moyasar
    account (Rail 2, #206).

    ``gateway_ref`` is the original charge's gateway reference (the Moyasar payment
    id stored on the ``Subscription_payments`` row); ``agent_moyasar_key`` is the
    owning agent's **decrypted** Moyasar secret key. The refund routes through the
    same gateway the charge did — the agent's account when a key is present, else
    the deterministic sandbox gateway so the flow stays demonstrable on un-onboarded
    installs (OPS-08). A declined/failed refund raises :class:`SubscriptionRefundError`
    so the caller returns 402 and records no refund row.
    """
    from services.payment_gateway import (
        GatewayNotConfigured,
        PaymentDeclined,
        recurring_gateway,
    )

    if not gateway_ref:
        raise SubscriptionRefundError("payment has no gateway reference to refund")

    key = (agent_moyasar_key or "").strip() or _platform_moyasar_key()
    gateway = recurring_gateway(key)

    try:
        result = await gateway.refund(gateway_ref, amount)
    except PaymentDeclined as exc:
        raise SubscriptionRefundError(f"Refund declined: {exc.reason}") from exc
    except GatewayNotConfigured as exc:
        raise SubscriptionRefundError(str(exc)) from exc

    if not result.approved:
        raise SubscriptionRefundError(
            f"Refund failed: {result.decline_reason or 'declined'}"
        )

    return RefundResult(
        refunded=True, method=result.gateway, reference=result.gateway_ref
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


async def reserve_subscription_period(
    *,
    client_id: int,
    payer_user_id: str,
    cycle: str,
    period_start: str,
    period_end: str,
    period_key: str,
) -> bool:
    """Reserve this billing period BEFORE charging (ISSUE-182), the compare-and-set
    that closes the double-charge window.

    The old guard charged first and only then INSERTed under
    ``uq_subscription_payment_client_period`` — two requests that both passed the
    SELECT pre-check each fired a *real* gateway charge and only the second INSERT
    was rejected, so the card was billed twice. Here the unique constraint gates the
    charge instead: exactly one caller INSERTs+commits a ``reserving`` placeholder
    for ``(client_id, period_key)`` and is cleared to charge; a concurrent caller
    loses the INSERT and gets ``False`` — it must NOT charge. Mirrors the aggregator
    settle lock (REV-05).

    Runs in its OWN short-lived session and commits, so (a) the reservation is durable
    and visible to a concurrent settler on another connection (a manual pay racing the
    scheduler sweep) before the slow gateway charge, and (b) a lost CAS never poisons
    the caller's session (an IntegrityError mid-flush would otherwise strand it). A
    reservation orphaned by a crash before finalise/release is reclaimed by
    :func:`release_stale_subscription_reservations`. Returns whether this caller won.
    """
    from datetime import datetime, timezone

    from sqlalchemy.exc import IntegrityError

    from core.database import db_manager
    from models.subscription_payments import Subscription_payments

    async with db_manager.async_session_maker() as db:
        db.add(
            Subscription_payments(
                user_id=str(payer_user_id),
                client_id=client_id,
                amount=0,
                billing_cycle=cycle,
                period_start=period_start,
                period_key=period_key,
                period_end=period_end,
                method=RESERVING_METHOD,
                reference=None,
                # Aware-UTC stamp so the stale-reservation sweep compares consistently.
                created_at=datetime.now(timezone.utc),
            )
        )
        try:
            await db.commit()
        except IntegrityError:
            return False
    return True


async def release_subscription_reservation(*, client_id: int, period_key: str) -> None:
    """Release a reservation whose charge never settled (decline/error), so the period
    is open for a later retry (ISSUE-182). Runs in its own session; a no-op once
    finalised (the row is no longer ``reserving``)."""
    from sqlalchemy import delete

    from core.database import db_manager
    from models.subscription_payments import Subscription_payments

    async with db_manager.async_session_maker() as db:
        await db.execute(
            delete(Subscription_payments).where(
                Subscription_payments.client_id == client_id,
                Subscription_payments.period_key == period_key,
                Subscription_payments.method == RESERVING_METHOD,
            )
        )
        await db.commit()


async def release_stale_subscription_reservations(
    db, *, threshold_seconds: int = 600, now=None
) -> int:
    """Reclaim reservations stranded in ``reserving`` past ``threshold_seconds`` —
    a settling caller that crashed after the reserve commit but before finalise/release
    (ISSUE-182). Without this the orphaned ``(client, period_key)`` row would block
    that period's charge forever. Mirrors :func:`services.aggregator.recover_stuck_aggregator_claims`.
    Returns the number reclaimed. Runs at the top of the dunning sweep."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete

    from models.subscription_payments import Subscription_payments

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=threshold_seconds)
    result = await db.execute(
        delete(Subscription_payments).where(
            Subscription_payments.method == RESERVING_METHOD,
            Subscription_payments.created_at < cutoff,
        )
    )
    await db.commit()
    return result.rowcount or 0


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
    period_key: Optional[str] = None,
    reservation: bool = False,
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
    # REV-04: the settled-period idempotency key is the billing-period boundary
    # (``period_key``), not ``period_start`` (the calendar day this charge ran). A
    # cross-midnight concurrent race for the same period thus collides on
    # uq_subscription_payment_client_period instead of slipping through on two
    # distinct per-day keys. Callers pass the boundary; fall back to period_start
    # only for legacy callers that omit it.
    settled_key = period_key if period_key is not None else period_start

    reserved_row = None
    if reservation:
        # ISSUE-182 finalise: the period was reserved (committed by reserve_subscription_period
        # on its own connection) before the charge. Load that ``reserving`` placeholder
        # and rewrite it into the real payment rather than inserting (and racing) again.
        reserved_row = await existing_settled_payment(
            db, client_id=merchant.id, period_key=settled_key
        )
    if reserved_row is not None:
        reserved_row.amount = collected
        reserved_row.method = charge.method
        reserved_row.reference = charge.reference
        payment = reserved_row
    else:
        payment = Subscription_payments(
            user_id=str(payer_user_id),
            client_id=merchant.id,
            amount=collected,
            billing_cycle=cycle,
            period_start=period_start,
            period_key=settled_key,
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
                db, client_id=merchant.id, period_key=settled_key
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
