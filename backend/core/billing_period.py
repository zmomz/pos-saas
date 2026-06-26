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
