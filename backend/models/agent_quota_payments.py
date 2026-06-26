"""Agent quota payments — the platform's own revenue ledger (Rail 1).

The platform sells each white-label agent a fixed-price quota of client slots
(the package ``wholesale_price``). When the agent pays for / renews that quota —
through the **platform's** Moyasar account — one row is written here. This is the
*only* money that is the platform's: the agent reselling subscriptions to his
merchants and collecting that himself (Rail 2) never touches this ledger.

Backs the master console's platform-revenue figure and the agent's own
quota-payment history. Mirror of ``subscription_payments`` but at agent grain.
"""
from core.database import Base
from core.money import Money
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String, UniqueConstraint


class Agent_quota_payments(Base):
    __tablename__ = "agent_quota_payments"
    __table_args__ = (
        # FIN-04: one settled quota charge per billing period per agent (mirror of
        # subscription_payments). The recurring settlement sets ``period_key`` to
        # the period start; a re-charge race for the same period conflicts here.
        # Manual records leave it NULL (NULLs distinct → no collision).
        UniqueConstraint(
            "agent_id", "period_key", name="uq_quota_payment_agent_period"
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    # The agent's login account (scoping key, like every other entity).
    user_id = Column(String, nullable=False, index=True)
    agent_id = Column(Integer, nullable=False, index=True)
    amount = Column(Money, nullable=False)
    billing_cycle = Column(String, nullable=True)
    period_start = Column(String, nullable=True)
    period_end = Column(String, nullable=True)
    # FIN-04: settled-period idempotency key (the period start) for an actual
    # recurring quota charge; NULL for manual records (exempt).
    period_key = Column(String, nullable=True)
    # 'moyasar' when charged through the platform gateway; 'manual' for an
    # off-card / bank-transfer quota deal the master records by hand.
    method = Column(String, nullable=True, default='moyasar')
    # Moyasar payment id when charged through the gateway; null for manual records.
    reference = Column(String, nullable=True)
    note = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
