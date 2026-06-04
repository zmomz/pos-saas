"""Commission / revenue-split ledger (RSL-01..04, F-029).

The three-tier hierarchy is master → agent (white-label reseller) → client
(merchant). An agent buys a slot bundle from the master at the package
``wholesale_price`` and resells each client a subscription at their own
``subscription_fee``. The agent's margin — and the amount owed back to the
platform master — was never computed: ``pay_client_subscription`` only recorded
the gross fee in ``subscription_payments``, and the Agent Dashboard summed
``subscription_fee`` client-side (gross, no margin). This was the central
Product-B gap.

Each time a client pays (CL-04) one of these rows is written **atomically with
the payment**, decomposing the gross fee into:

* ``master_cut``  — the platform's share, the per-client amortized wholesale
  (``wholesale_price / client_slots`` of the agent's package), clamped to the
  gross so the master never claims more than was collected;
* ``agent_net``   — the reseller's margin, ``gross - master_cut``.

The invariant **``master_cut + agent_net == gross``** always holds (see
``services/commission.py::compute_commission_split``), so the ledger reconciles.

Every row carries ``user_id`` (the **agent's** login account) so reads scope to
the owning reseller exactly like every other entity — one agent can never see
another agent's revenue (SEC-02). ``GET /tenant/agent/revenue`` aggregates these
rows; the master economics rollup (MA-08 / RSL-08) is a separate finding (F-023).
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String

from core.database import Base


class Commission_ledger(Base):
    __tablename__ = "commission_ledger"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    # The owning agent's login account (scoping key, like every other entity).
    user_id = Column(String, nullable=False, index=True)
    agent_id = Column(Integer, nullable=False, index=True)
    client_id = Column(Integer, nullable=False, index=True)
    # The settled subscription payment this split decomposes (1:1).
    subscription_payment_id = Column(Integer, nullable=False, index=True)
    # The agent's package at pay time (wholesale source); null if unresolved.
    package_id = Column(Integer, nullable=True)
    gross = Column(Float, nullable=False, default=0, server_default="0")
    master_cut = Column(Float, nullable=False, default=0, server_default="0")
    agent_net = Column(Float, nullable=False, default=0, server_default="0")
    billing_cycle = Column(String, nullable=True)
    period_start = Column(String, nullable=True)
    period_end = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
