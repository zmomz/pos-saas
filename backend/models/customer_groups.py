"""Customer groups & membership tiers (CRM, #221).

A customer group is a named segment a merchant assigns customers to — "Wholesale",
"VIP", "Staff" — each carrying a ``tier`` label (e.g. bronze/silver/gold) and an
optional default discount the group earns. A customer belongs to at most one group
via ``customers.group_id``; the group drives tiered pricing and targeted campaigns.

Owner-scoped (SEC-02): every group carries the owning merchant's ``user_id`` (and
advisory ``client_id``) so one tenant can neither see nor assign into another
tenant's groups.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String

from core.database import Base


class CustomerGroup(Base):
    __tablename__ = "customer_groups"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    # ARC-05: advisory within-tenant narrowing, parity with the core tables.
    client_id = Column(Integer, nullable=True, index=True)
    name = Column(String, nullable=False)
    # Membership tier label (bronze/silver/gold/vip/…). Free-form so each merchant
    # names their ladder; null ⇒ an untiered named group.
    tier = Column(String, nullable=True)
    # Optional default discount the group earns at the till (e.g. wholesale 10%).
    # Stored here as the source of truth; sale-time application is a later slice.
    discount_percent = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
