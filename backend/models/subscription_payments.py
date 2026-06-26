from core.database import Base
from core.money import Money
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String, UniqueConstraint


class Subscription_payments(Base):
    """A single subscription payment by a client merchant (CL-04 payment history).

    Recorded whenever a client pays their subscription. The ledger backs the
    client dashboard's payment-history panel and the next-billing advance.
    """

    __tablename__ = "subscription_payments"
    __table_args__ = (
        # FIN-04: one settled gateway charge per billing period per client. The
        # recurring settlement sets ``period_key`` to the period start; a double-
        # click or scheduler-vs-manual race for the same period conflicts here and
        # reconciles to the first payment instead of charging again. Proration /
        # manual records leave ``period_key`` NULL — NULLs are distinct, so those
        # never collide.
        UniqueConstraint(
            "client_id", "period_key", name="uq_subscription_payment_client_period"
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    client_id = Column(Integer, nullable=False)
    amount = Column(Money, nullable=False)
    billing_cycle = Column(String, nullable=True)
    period_start = Column(String, nullable=True)
    period_end = Column(String, nullable=True)
    # FIN-04: the settled-period idempotency key (the period start) for an actual
    # recurring gateway charge; NULL for proration/manual records (exempt).
    period_key = Column(String, nullable=True)
    method = Column(String, nullable=True, default='manual')
    # Moyasar payment id when charged through the gateway (CL-04, Rail 2); null for
    # manually-settled payments.
    reference = Column(String, nullable=True)
    note = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
