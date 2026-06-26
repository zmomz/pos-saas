from core.database import Base
from core.money import Money
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String


class Subscription_payments(Base):
    """A single subscription payment by a client merchant (CL-04 payment history).

    Recorded whenever a client pays their subscription. The ledger backs the
    client dashboard's payment-history panel and the next-billing advance.
    """

    __tablename__ = "subscription_payments"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    client_id = Column(Integer, nullable=False)
    amount = Column(Money, nullable=False)
    billing_cycle = Column(String, nullable=True)
    period_start = Column(String, nullable=True)
    period_end = Column(String, nullable=True)
    method = Column(String, nullable=True, default='manual')
    # Moyasar payment id when charged through the gateway (CL-04, Rail 2); null for
    # manually-settled payments.
    reference = Column(String, nullable=True)
    note = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
