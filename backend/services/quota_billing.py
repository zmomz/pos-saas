"""Agent quota billing — the platform's own revenue rail (Rail 1).

The platform sells each white-label agent a fixed-price **quota** of client slots
(the package ``wholesale_price``). This module charges the agent for that quota
through the **platform's** Moyasar account (``MOYASAR_API_KEY``) against the
agent's stored card-on-file, and runs the agent-side dunning sweep when a renewal
fails. This is the only money that is the platform's — the agent collecting
subscriptions from his merchants (Rail 2, ``services.subscription_billing``) is the
agent's own revenue and never touches this rail.

Cascade (confirmed policy): an agent who fails to pay for his quota is suspended
(``quota_status='suspended'`` + ``is_active=False``), which blocks him at auth and
takes his merchants dark with him — he hasn't paid for the capacity they run on.

The state walk reuses the pure :func:`services.dunning.next_dunning_state`:

    active --fail--> past_due --fail--> dunning --fail(grace exhausted)--> suspended
       ^                                                                       |
       +------------------------------- pay / successful retry ----------------+
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_, select, update

from core.config import settings
from models.agent_quota_payments import Agent_quota_payments
from models.agents import Agents
from models.audit_logs import Audit_logs
from services.dunning import _grace_days, _max_retries, next_dunning_state

logger = logging.getLogger(__name__)

# The non-terminal quota states a dunning sweep retries.
ACTIVE_STATES = ("active", "past_due", "dunning")


class QuotaChargeError(Exception):
    """A Moyasar quota charge was attempted and declined/failed."""


class QuotaCardUnreadable(QuotaChargeError):
    """The agent HAS a quota card-on-file token but it could not be decrypted —
    a crypto/key fault, not a missing card. The dunning sweep must treat this as
    an ops alert and SKIP (not advance) dunning, never as a decline (FIN-06).

    Subclasses :class:`QuotaChargeError` so existing ``except QuotaChargeError``
    callers (e.g. the manual quota-pay endpoint) keep surfacing it as a failure;
    only the dunning loop catches it first to skip instead of suspend.
    """


@dataclass
class QuotaChargeResult:
    charged: bool
    status: str  # "paid"
    method: str  # "moyasar" | "sandbox"
    reference: Optional[str]


def _platform_moyasar_key() -> str:
    return (getattr(settings, "moyasar_api_key", "") or "").strip()


def _advance(start: datetime, cycle: str) -> str:
    days = 365 if (cycle or "monthly") == "yearly" else 30
    return (start + timedelta(days=days)).date().isoformat()


async def charge_quota(
    agent: Agents,
    *,
    amount: Optional[float] = None,
    currency: str = "SAR",
    idempotency_key: Optional[str] = None,
) -> QuotaChargeResult:
    """Charge the agent's quota fee through the PLATFORM's Moyasar account.

    ``amount`` falls back to the agent's ``quota_price``. Uses the agent's stored
    card-on-file token. Fails closed: live billing with no card on file raises
    :class:`QuotaChargeError` (the sandbox synthesizes its own approval so the flow
    is demonstrable without a real platform key).
    """
    from services.payment_gateway import (
        GatewayNotConfigured,
        PaymentDeclined,
        SandboxGateway,
        recurring_gateway,
    )

    fee = float(agent.quota_price or 0) if amount is None else float(amount)
    gateway = recurring_gateway(_platform_moyasar_key())

    card_token = None
    if getattr(agent, "quota_card_token_enc", None):
        from core.crypto import decrypt_secret

        try:
            card_token = decrypt_secret(agent.quota_card_token_enc)
        except Exception as exc:  # present but unreadable — a key/crypto fault, NOT "no card"
            raise QuotaCardUnreadable(
                "Quota card-on-file token is present but could not be decrypted"
            ) from exc

    if not isinstance(gateway, SandboxGateway) and not card_token:
        raise QuotaChargeError("No card on file for the agent's quota")

    try:
        result = await gateway.charge(
            amount=fee,
            tender_type="card",
            currency=currency,
            token=card_token,
            metadata={
                "recurring": True,
                "description": f"Quota (agent {agent.id})",
                "agent_id": str(agent.id),
                "idempotency_key": idempotency_key,
            },
        )
    except PaymentDeclined as exc:
        raise QuotaChargeError(f"Card declined: {exc.reason}") from exc
    except GatewayNotConfigured as exc:
        raise QuotaChargeError(str(exc)) from exc

    if not result.approved:
        raise QuotaChargeError(f"Card declined: {result.decline_reason or 'declined'}")

    return QuotaChargeResult(
        charged=True, status="paid", method=result.gateway, reference=result.gateway_ref
    )


async def record_quota_payment(
    db,
    agent: Agents,
    *,
    charge: QuotaChargeResult,
    cycle: str,
    period_start: str,
    period_end: str,
    amount: Optional[float] = None,
):
    """Persist a settled quota payment, advance the agent's quota period, and clear
    any quota-dunning state (status -> active, agent re-activated). Runs in the
    caller's transaction (no commit). Returns the persisted payment row.
    """
    collected = float(agent.quota_price or 0) if amount is None else float(amount)
    payment = Agent_quota_payments(
        user_id=str(agent.user_id),
        agent_id=agent.id,
        amount=collected,
        billing_cycle=cycle,
        period_start=period_start,
        period_end=period_end,
        method=charge.method,
        reference=charge.reference,
    )
    db.add(payment)
    await db.flush()  # assign the payment id

    await db.execute(
        update(Agents)
        .where(Agents.id == agent.id)
        .values(
            quota_status="active",
            next_quota_billing_date=period_end,
            quota_dunning_attempts=0,
            quota_grace_deadline=None,
            is_active=True,
        )
    )
    return payment


async def _send_quota_notice(agent: Agents, action: str, grace_deadline: Optional[str]) -> None:
    """Best-effort Arabic reminder / suspension notice to the agent. Never raises
    (graceful degradation, OPS-08): with no SMTP configured it just logs."""
    try:
        from core.email import send_email

        fee = float(agent.quota_price or 0)
        if action == "suspended":
            subject = "تعليق الحساب — Account suspended"
            body = (
                f"عزيزنا {agent.company_name}،\n\n"
                f"تم تعليق حسابك بعد تعذّر تحصيل رسوم الباقة المستحقة ({fee:.2f} ⃁).\n"
                "يرجى سداد المبلغ المتأخر لإعادة تفعيل حسابك وحسابات عملائك.\n"
            )
        else:
            subject = "تذكير بسداد رسوم الباقة — Quota payment reminder"
            body = (
                f"عزيزنا {agent.company_name}،\n\n"
                f"لم نتمكن من تحصيل رسوم باقتك المستحقة ({fee:.2f} ⃁).\n"
                f"يرجى السداد قبل {grace_deadline or '—'} لتفادي تعليق الحساب.\n"
            )
        await send_email(agent.email, subject, body)
    except Exception as exc:  # pragma: no cover - notice must never block dunning
        logger.warning("Quota dunning notice failed (%s); continuing", type(exc).__name__)


async def run_agent_quota_dunning(
    db,
    agent: Agents,
    *,
    actor_user_id: str,
    now: Optional[datetime] = None,
    max_retries: Optional[int] = None,
    grace_days: Optional[int] = None,
) -> dict:
    """Attempt one quota dunning step for a single overdue agent.

    Charges the quota fee; on success records the payment + recovers the account,
    on failure advances the quota-dunning state (and on suspension, cascades:
    ``is_active=False`` blocks the agent and his merchants at auth). Persists the
    new state + an audit row in the caller's transaction (no commit).
    """
    now = now or datetime.now(timezone.utc)
    max_retries = max_retries if max_retries is not None else _max_retries()
    grace_days = grace_days if grace_days is not None else _grace_days()
    cycle = agent.quota_cycle or "monthly"
    period_start = now.date().isoformat()
    period_end = _advance(now, cycle)

    charge_ok = True
    charge = None
    try:
        charge = await charge_quota(
            agent, idempotency_key=f"quota-{agent.id}-{period_start}"
        )
    except QuotaCardUnreadable:
        # FIN-06: the agent's quota card token is present but undecryptable — a
        # crypto/key fault, not a decline. Skip dunning (leave the agent's state
        # untouched, so suspension never cascades his merchants dark over a key
        # problem) and raise an operational alert for ops to fix the key.
        logger.error(
            "Quota dunning skipped for agent %s: card token present but "
            "undecryptable; not advancing dunning (FIN-06)",
            agent.id,
        )
        db.add(
            Audit_logs(
                user_id=str(actor_user_id),
                action="QUOTA_DUNNING_DECRYPT_ERROR",
                entity_type="agents",
                entity_id=str(agent.id),
                details=f"unreadable=quota card token status={agent.quota_status}",
            )
        )
        return {
            "agent_id": agent.id,
            "action": "skipped",
            "status": agent.quota_status,
            "attempts": agent.quota_dunning_attempts,
            "grace_deadline": None,
        }
    except QuotaChargeError:
        charge_ok = False

    transition = next_dunning_state(
        agent.quota_status, agent.quota_dunning_attempts, charge_ok=charge_ok, max_retries=max_retries
    )

    if charge_ok and charge is not None:
        await record_quota_payment(
            db, agent, charge=charge, cycle=cycle, period_start=period_start, period_end=period_end
        )
        grace_deadline = None
    else:
        grace_deadline = (now + timedelta(days=grace_days)).date().isoformat()
        await db.execute(
            update(Agents)
            .where(Agents.id == agent.id)
            .values(
                quota_status=transition.status,
                quota_dunning_attempts=transition.attempts,
                # Cascade: a suspended agent (and thus his merchants) is blocked at
                # auth; a still-in-grace agent stays active.
                is_active=transition.is_active,
                quota_grace_deadline=grace_deadline,
            )
        )
        await _send_quota_notice(agent, transition.action, grace_deadline)

    db.add(
        Audit_logs(
            user_id=str(actor_user_id),
            action=f"QUOTA_DUNNING_{transition.action.upper()}",
            entity_type="agents",
            entity_id=str(agent.id),
            details=f"attempts={transition.attempts} status={transition.status}",
        )
    )

    return {
        "agent_id": agent.id,
        "action": transition.action,
        "status": transition.status,
        "attempts": transition.attempts,
        "grace_deadline": grace_deadline,
    }


async def run_global_quota_dunning(
    db,
    *,
    actor_user_id: str = "system:billing-scheduler",
    now: Optional[datetime] = None,
) -> dict:
    """Run the quota dunning/retry sweep across EVERY overdue agent in one pass —
    the always-on scheduler's Rail 1 entry point (mirrors merchant dunning).

    Selects agents with a positive quota price whose quota is non-terminal and
    either already in the past_due/dunning window or whose billing date has passed.
    Commits the whole batch once.
    """
    now = now or datetime.now(timezone.utc)
    today = now.date().isoformat()

    rows = (
        await db.execute(
            select(Agents).where(
                Agents.quota_price.isnot(None),
                Agents.quota_price > 0,
                or_(
                    Agents.quota_status.in_(("past_due", "dunning")),
                    Agents.next_quota_billing_date.is_(None),
                    Agents.next_quota_billing_date <= today,
                ),
                or_(Agents.quota_status.in_(ACTIVE_STATES), Agents.quota_status.is_(None)),
            )
        )
    ).scalars().all()

    summary = {"processed": 0, "recovered": 0, "past_due": 0, "dunning": 0, "suspended": 0}
    for agent in rows:
        result = await run_agent_quota_dunning(db, agent, actor_user_id=actor_user_id, now=now)
        summary["processed"] += 1
        summary[result["action"]] = summary.get(result["action"], 0) + 1

    await db.commit()
    return summary
