"""Lightweight SMS delivery (Phase 3 — POS-04 invoice send, feature-gated).

Mirrors :mod:`core.email`: real delivery is attempted via the Twilio REST API
only when ``TWILIO_ACCOUNT_SID`` / ``TWILIO_AUTH_TOKEN`` / ``TWILIO_FROM`` are
configured; otherwise it logs the message and returns ``False`` (dev fallback) so
nothing breaks when SMS is not set up. Never raises.

Twilio is called over plain ``httpx`` (no extra dependency) so the provider is
optional at install time.
"""
import logging

from core.config import settings

logger = logging.getLogger(__name__)

_TWILIO_API = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"


def _twilio_configured() -> bool:
    return bool(
        getattr(settings, "twilio_account_sid", None)
        and getattr(settings, "twilio_auth_token", None)
        and getattr(settings, "twilio_from", None)
    )


async def send_sms(to_number: str, body: str) -> bool:
    """Send an SMS. Returns True if delivered via Twilio, False on dev fallback.

    Never raises — a receipt SMS must not fail the request that triggered it.
    """
    to_number = (to_number or "").strip()
    if not to_number:
        logger.info("SMS skipped: empty destination number.")
        return False

    if not _twilio_configured():
        logger.info("SMS (dev fallback) → %s | %s", to_number, body[:80])
        return False

    sid = getattr(settings, "twilio_account_sid")
    token = getattr(settings, "twilio_auth_token")
    sender = getattr(settings, "twilio_from")
    try:
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                _TWILIO_API.format(sid=sid),
                data={"To": to_number, "From": sender, "Body": body},
                auth=(sid, token),
            )
        if resp.status_code in (200, 201):
            logger.info("SMS sent → %s", to_number)
            return True
        logger.warning("Twilio SMS send failed (status %s); dev fallback", resp.status_code)
        return False
    except Exception as exc:  # pragma: no cover - network/Twilio failure path
        logger.warning("SMS send failed (%s); falling back to dev mode", type(exc).__name__)
        return False
