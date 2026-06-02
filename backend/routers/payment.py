"""Stripe payment endpoints.

Wires the previously-orphaned `services/payment.py` (Stripe checkout/subscription)
into the HTTP layer. When ``STRIPE_SECRET_KEY`` is not configured the endpoints
return 503 rather than failing obscurely.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from core.config import settings
from dependencies.auth import get_current_user
from schemas.auth import UserResponse
from services.payment import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    CheckoutStatusResponse,
    CheckoutError,
    PaymentService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


def _require_stripe_configured() -> None:
    if not getattr(settings, "stripe_secret_key", None):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payments are not configured. Set STRIPE_SECRET_KEY to enable.",
        )


def _payment_error(exc: CheckoutError) -> HTTPException:
    code = (
        status.HTTP_400_BAD_REQUEST
        if exc.error_type in ("validation", "card_error")
        else status.HTTP_502_BAD_GATEWAY
    )
    return HTTPException(status_code=code, detail=str(exc))


@router.post("/checkout", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    request: CheckoutSessionRequest,
    current_user: UserResponse = Depends(get_current_user),
):
    """Create a Stripe Checkout session (payment or subscription)."""
    _require_stripe_configured()
    service = PaymentService()
    try:
        return await service.create_checkout_session(request)
    except CheckoutError as exc:
        logger.warning("Stripe checkout failed: %s", exc.error_type)
        raise _payment_error(exc)


@router.get("/status/{session_id}", response_model=CheckoutStatusResponse)
async def get_checkout_status(
    session_id: str,
    current_user: UserResponse = Depends(get_current_user),
):
    """Retrieve the status of a Stripe Checkout session."""
    _require_stripe_configured()
    service = PaymentService()
    try:
        return await service.get_checkout_status(session_id)
    except CheckoutError as exc:
        logger.warning("Stripe status lookup failed: %s", exc.error_type)
        raise _payment_error(exc)
