"""Preference-honoring notification delivery (ISSUE-077).

The in-app notification *center* (``models.notifications``) persists the alert
feed. This dispatcher delivers those alerts out-of-band over a real channel,
honoring each user's ``UserProfile`` notification preferences.

Channel today is **email** — the only channel for which the account carries a
destination (``User.email``); SMS/push are deferred until the profile gains a
phone/device-token plus its own toggle. The preference model is:

  * ``email_alerts``  — the email **channel** master switch (off ⇒ no email).
  * ``low_stock_alerts`` / ``transaction_alerts`` / ``daily_summary`` — per-category
    switches; an alert of that category is delivered only when its switch is on.

Types without a category switch (``zatca_failed`` / ``subscription`` / ``system``)
ride the channel switch alone. Delivery is best-effort and never raises: a missing
profile falls back to the shipped defaults, and a channel adapter that can't
deliver (dev/no-SMTP) is reported as ``"fallback"``, never an error.
"""
import logging

from core.email import send_email
from schemas.auth import NotificationPrefs
from services.user import UserService

logger = logging.getLogger(__name__)

# Notification ``type`` → the per-category preference flag that gates it. Types
# absent here ride the channel switch alone.
_CATEGORY_PREF = {
    "low_stock": "low_stock_alerts",
    "transaction": "transaction_alerts",
    "daily_summary": "daily_summary",
}


def _effective_prefs(profile) -> NotificationPrefs:
    """The user's notification toggles, falling back to the shipped defaults when
    they have never saved a profile (so e.g. ``daily_summary`` stays off)."""
    if profile is None:
        return NotificationPrefs()
    return NotificationPrefs(
        email_alerts=profile.email_alerts,
        low_stock_alerts=profile.low_stock_alerts,
        daily_summary=profile.daily_summary,
        transaction_alerts=profile.transaction_alerts,
    )


class NotificationDispatcher:
    @staticmethod
    async def dispatch(db, user_id, *, type, title, message) -> dict:
        """Deliver one alert over each enabled channel, honoring the user's prefs.

        Returns a per-channel status map, e.g. ``{"email": "sent"}`` /
        ``{"email": "fallback"}`` / ``{"email": "skipped"}``.
        """
        prefs = _effective_prefs(await UserService.get_preferences(db, user_id))

        category_pref = _CATEGORY_PREF.get(type)
        category_on = getattr(prefs, category_pref) if category_pref is not None else True

        if not prefs.email_alerts or not category_on:
            return {"email": "skipped"}

        user = await UserService.get_user_profile(db, user_id)
        to_email = user.email if user is not None else None
        if not to_email:
            return {"email": "skipped"}

        delivered = await send_email(to_email, title or "Notification", message)
        return {"email": "sent" if delivered else "fallback"}
