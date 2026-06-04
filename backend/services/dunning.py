"""Subscription dunning state machine (CL-06, finding F-028).

A merchant whose subscription charge fails must not jump straight to a hard
suspend. The category leaders (and the SRS) run a *dunning* schedule: the first
failure marks the account ``past_due``, subsequent failed retries escalate it to
``dunning`` (a grace window with reminder notices), and only an exhausted grace
window finally ``suspended``s the merchant (blocked at auth until they pay). A
successful charge at any point recovers the account to ``active`` and advances
billing — recorded exactly like a manual pay (CL-04) via
``services.subscription_billing.record_settled_payment``.

The state walk is::

    active --fail--> past_due --fail--> dunning --fail(grace exhausted)--> suspended
       ^                                                                       |
       +------------------------------- pay / successful retry ----------------+

``next_dunning_state`` is a pure function (no DB / no gateway) so the transition
table is unit-testable in isolation; ``run_client_dunning`` / ``run_agent_dunning``
wrap it with the real charge attempt, persistence, an audit row, and a best-effort
Arabic reminder notice (PRN-09).

There is no always-on scheduler on the standalone deployment, so the sweep is
agent-triggered (``POST /tenant/agent/billing/run-dunning``) — the same
operator-drains-the-backlog pattern used by the ZATCA reconcile sweep (F-020).
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_, select, update

from core.config import settings
from models.agents import Agents
from models.audit_logs import Audit_logs
from models.clients import Clients
from services.subscription_billing import (
    SubscriptionChargeError,
    charge_subscription,
    record_settled_payment,
)

logger = logging.getLogger(__name__)

# Number of consecutive failed charge attempts tolerated before the account is
# suspended. With the default 3: fail#1 -> past_due, fail#2 -> dunning,
# fail#3 -> suspended. Configurable via the DUNNING_MAX_RETRIES env var.
DEFAULT_MAX_RETRIES = 3
# Days of grace granted on each escalation before the next retry should run.
DEFAULT_GRACE_DAYS = 7

# The non-terminal subscription states a dunning sweep retries.
ACTIVE_STATES = ("active", "past_due", "dunning")


def _max_retries() -> int:
    try:
        return max(2, int(getattr(settings, "dunning_max_retries", DEFAULT_MAX_RETRIES) or DEFAULT_MAX_RETRIES))
    except (TypeError, ValueError):
        return DEFAULT_MAX_RETRIES


def _grace_days() -> int:
    try:
        return max(1, int(getattr(settings, "dunning_grace_days", DEFAULT_GRACE_DAYS) or DEFAULT_GRACE_DAYS))
    except (TypeError, ValueError):
        return DEFAULT_GRACE_DAYS


@dataclass
class DunningTransition:
    status: str  # active | past_due | dunning | suspended
    attempts: int  # consecutive failed-charge counter after this transition
    is_active: bool  # False only once suspended (blocks the merchant at auth)
    action: str  # recovered | past_due | dunning | suspended


def next_dunning_state(
    status: Optional[str],
    attempts: Optional[int],
    *,
    charge_ok: bool,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> DunningTransition:
    """Pure transition: given the current state and a charge outcome, return the
    next state. A success always recovers to ``active`` (counter reset). Each
    failure increments the counter and escalates one step; once the counter
    reaches ``max_retries`` the account is suspended."""
    if charge_ok:
        return DunningTransition(status="active", attempts=0, is_active=True, action="recovered")

    new_attempts = int(attempts or 0) + 1
    if new_attempts >= max_retries:
        return DunningTransition(
            status="suspended", attempts=new_attempts, is_active=False, action="suspended"
        )
    if new_attempts == 1:
        return DunningTransition(
            status="past_due", attempts=new_attempts, is_active=True, action="past_due"
        )
    return DunningTransition(
        status="dunning", attempts=new_attempts, is_active=True, action="dunning"
    )


def _advance(start: datetime, cycle: str) -> str:
    days = 365 if (cycle or "monthly") == "yearly" else 30
    return (start + timedelta(days=days)).date().isoformat()


async def _send_dunning_notice(merchant: Clients, transition: DunningTransition, grace_deadline: Optional[str]) -> None:
    """Best-effort Arabic reminder / suspension notice (PRN-09). Never raises —
    graceful degradation (OPS-08): with no SMTP configured it just logs."""
    try:
        from core.email import send_email

        fee = float(merchant.subscription_fee or 0)
        if transition.action == "suspended":
            subject = "تعليق الاشتراك — Subscription suspended"
            body = (
                f"عزيزنا {merchant.business_name}،\n\n"
                f"تم تعليق اشتراكك بعد تعذّر تحصيل الرسوم المستحقة ({fee:.2f} ر.س).\n"
                "يرجى سداد المبلغ المتأخر لإعادة تفعيل حسابك.\n"
            )
        else:
            subject = "تذكير بسداد الاشتراك — Subscription payment reminder"
            body = (
                f"عزيزنا {merchant.business_name}،\n\n"
                f"لم نتمكن من تحصيل رسوم اشتراكك المستحقة ({fee:.2f} ر.س).\n"
                f"يرجى السداد قبل {grace_deadline or '—'} لتفادي تعليق الحساب.\n"
            )
        await send_email(merchant.email, subject, body)
    except Exception as exc:  # pragma: no cover - notice must never block dunning
        logger.warning("Dunning notice failed (%s); continuing", type(exc).__name__)


async def run_client_dunning(
    db,
    merchant: Clients,
    *,
    actor_user_id: str,
    agent_row: Optional[Agents] = None,
    now: Optional[datetime] = None,
    max_retries: Optional[int] = None,
    grace_days: Optional[int] = None,
) -> dict:
    """Attempt one dunning step for a single overdue merchant.

    Charges the subscription fee; on success records the payment + recovers the
    account, on failure advances the dunning state. Persists the new state and an
    audit row in the caller's transaction (no commit). Returns a per-client
    summary.
    """
    now = now or datetime.now(timezone.utc)
    max_retries = max_retries if max_retries is not None else _max_retries()
    grace_days = grace_days if grace_days is not None else _grace_days()
    cycle = merchant.billing_cycle or "monthly"
    period_start = now.date().isoformat()
    period_end = _advance(now, cycle)

    agent_stripe_account = getattr(agent_row, "stripe_account_id", None) if agent_row is not None else None

    charge_ok = True
    charge = None
    try:
        charge = await charge_subscription(
            amount=float(merchant.subscription_fee or 0),
            currency=str(getattr(settings, "subscription_currency", "sar") or "sar"),
            agent_stripe_account=agent_stripe_account,
            client_id=merchant.id,
            idempotency_key=f"dun-{merchant.id}-{period_start}",
        )
    except SubscriptionChargeError:
        charge_ok = False

    transition = next_dunning_state(
        merchant.subscription_status, merchant.dunning_attempts, charge_ok=charge_ok, max_retries=max_retries
    )

    if charge_ok and charge is not None:
        # Successful retry: record the payment and recover (status -> active,
        # billing advanced, dunning cleared) exactly like a manual pay.
        await record_settled_payment(
            db,
            merchant=merchant,
            payer_user_id=str(merchant.user_id),
            charge=charge,
            cycle=cycle,
            period_start=period_start,
            period_end=period_end,
            agent_row=agent_row,
        )
        grace_deadline = None
    else:
        grace_deadline = (now + timedelta(days=grace_days)).date().isoformat()
        await db.execute(
            update(Clients)
            .where(Clients.id == merchant.id)
            .values(
                subscription_status=transition.status,
                dunning_attempts=transition.attempts,
                is_active=transition.is_active,
                grace_deadline=grace_deadline,
            )
        )
        await _send_dunning_notice(merchant, transition, grace_deadline)

    db.add(
        Audit_logs(
            user_id=str(actor_user_id),
            action=f"DUNNING_{transition.action.upper()}",
            entity_type="clients",
            entity_id=str(merchant.id),
            details=f"attempts={transition.attempts} status={transition.status}",
        )
    )

    return {
        "client_id": merchant.id,
        "action": transition.action,
        "status": transition.status,
        "attempts": transition.attempts,
        "grace_deadline": grace_deadline,
    }


async def run_agent_dunning(
    db,
    agent_id: int,
    *,
    actor_user_id: str,
    now: Optional[datetime] = None,
) -> dict:
    """Run a dunning sweep across all of one agent's overdue merchants.

    A merchant is *overdue* when its billing date has passed, or it is already in
    the ``past_due``/``dunning`` window (kept retried until it pays or is
    suspended). Already-suspended merchants are terminal until they pay and are
    skipped. Commits the whole batch once. Owner-scoped: only the agent's own
    clients are touched (SEC-02).
    """
    now = now or datetime.now(timezone.utc)
    today = now.date().isoformat()

    agent_row = (await db.execute(select(Agents).where(Agents.id == agent_id))).scalar_one_or_none()

    rows = (
        await db.execute(
            select(Clients).where(
                Clients.agent_id == agent_id,
                Clients.subscription_fee.isnot(None),
                Clients.subscription_fee > 0,
                Clients.subscription_status.in_(ACTIVE_STATES),
                or_(
                    Clients.subscription_status.in_(("past_due", "dunning")),
                    Clients.next_billing_date.is_(None),
                    Clients.next_billing_date <= today,
                ),
            )
        )
    ).scalars().all()

    summary = {"processed": 0, "recovered": 0, "past_due": 0, "dunning": 0, "suspended": 0}
    for merchant in rows:
        result = await run_client_dunning(
            db, merchant, actor_user_id=actor_user_id, agent_row=agent_row, now=now
        )
        summary["processed"] += 1
        summary[result["action"]] = summary.get(result["action"], 0) + 1

    await db.commit()
    return summary
