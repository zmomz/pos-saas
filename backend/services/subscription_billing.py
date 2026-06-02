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
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from core.config import settings

logger = logging.getLogger(__name__)


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
