"""Billing-period advance — anchor the next period to the original billing day.

A recurring charge advances the subscriber's ``next_billing_date`` by one cycle.
Naively advancing from ``now`` is wrong for an **early renewal**: when the merchant
pays while the current paid period still has unused days, ``now + cycle`` throws
those days away and walks the billing day forward every time someone pays a little
early (FIN-07).

The fix anchors the new period to the *current* period end (the existing
``next_billing_date``) whenever it is still in the future, so the unused remainder
of the paid period is preserved and the billing day stays fixed. When the current
period end is missing, unparseable, or already due/overdue (on or before today),
the anchor is today — an on-time renewal is unchanged and an overdue charge starts
from now.
"""
from datetime import date, datetime, timedelta
from typing import Optional, Union


def _cycle_days(cycle: Optional[str]) -> int:
    return 365 if (cycle or "monthly") == "yearly" else 30


def billing_period_key(
    next_billing_date: Optional[str],
    period_end: str,
) -> str:
    """Stable idempotency key for the billing period a recurring charge settles.

    A charge settles the period whose due date is the subscriber's current
    ``next_billing_date`` (the period boundary). Keying the settled payment on that
    boundary — rather than ``now.date()`` (FIN-04) — makes two concurrent charges
    for the same period collide on the ``(client_id, period_key)`` unique constraint
    even when they straddle midnight: both racers read the *same* boundary
    regardless of the wall-clock day, so the loser's insert is rejected and
    reconciles instead of charging the card a second time (REV-04). The boundary is
    used whether it is in the future (an early renewal) or the past (an overdue
    period) — both identify the period unambiguously.

    When no boundary is recorded yet — a brand-new subscription's first charge, or
    an unparseable date — the key is the ``period_end`` being established. That is
    the value ``next_billing_date`` advances *to*, so a same-day re-pay (which now
    reads that boundary) maps back to the same key and still reconciles to the one
    settled period instead of charging the freshly-advanced next period.
    """
    if next_billing_date:
        try:
            return date.fromisoformat(next_billing_date).isoformat()
        except ValueError:
            pass
    return period_end


def advance_billing_period(
    now: Union[datetime, date],
    current_period_end: Optional[str],
    cycle: Optional[str],
) -> str:
    """Return the next period end (ISO date), one ``cycle`` past the anchor.

    The anchor is ``current_period_end`` (the current ``next_billing_date``, an ISO
    date string) when it is still in the future — an early renewal then keeps the
    unused remainder of the paid period instead of forfeiting it (FIN-07). When
    ``current_period_end`` is missing, unparseable, or on/before today, the anchor
    is today: an on-time renewal is unchanged and an overdue charge starts from now.
    """
    today = now.date() if isinstance(now, datetime) else now
    anchor = today
    if current_period_end:
        try:
            parsed = date.fromisoformat(current_period_end)
        except ValueError:
            parsed = None
        if parsed is not None and parsed > today:
            anchor = parsed
    return (anchor + timedelta(days=_cycle_days(cycle))).isoformat()
