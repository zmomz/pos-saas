"""Stock counts & adjustments with reasons → variance record (INV-06, F-036).

Every POS category leader (Rewaa, Marn, Foodics) lets a merchant reconcile on-hand
stock against a physical count and record wastage/damage with a *reason*, leaving a
variance trail. The product had no such primitive — only the deprecated
``POST /inventory/deduct`` mutated stock with no reason/variance/audit.

A row here **is** the variance record: it snapshots the system on-hand
(``system_quantity``) at the moment of the count/adjustment, captures the new
physical count (``counted_quantity``), and stores the resulting
``variance = counted − system`` alongside the ``reason``. Applying the row sets the
stock pool to ``counted_quantity`` (the per-branch ledger when ``branch_id`` is
given — the pool the POS deducts from — else the client-level ``products.quantity``),
so the count and its audit trail land together.

Every row carries ``user_id`` (the merchant's own login account) so the handler
scopes reads/writes to the owner exactly like every other entity — one client can
never count or adjust another client's stock (SEC-02).

``stock_counts`` (a multi-line count *session* header that posts many adjustments at
once) is the convenience layer on top of this primitive and is deferred — this is
the atomic variance record INV-06 requires.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from core.database import Base


class Stock_adjustments(Base):
    __tablename__ = "stock_adjustments"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    # Null branch_id ⇒ a client-level adjustment (no per-branch ledger row).
    branch_id = Column(Integer, nullable=True)
    product_id = Column(Integer, nullable=False)
    # Denormalized name captured at adjustment time (the ledger keys off product_id).
    product_name = Column(String, nullable=True)
    # count / wastage / damage / correction / restock / other (INV-06 reasons).
    reason = Column(String, nullable=False, default="count", server_default="count")
    # On-hand the moment the count/adjustment was applied (the "system" figure).
    system_quantity = Column(Integer, nullable=False, default=0, server_default="0")
    # The new physical on-hand the count sets the pool to.
    counted_quantity = Column(Integer, nullable=False, default=0, server_default="0")
    # counted − system (negative for wastage/damage shrink, positive for a found gain).
    variance = Column(Integer, nullable=False, default=0, server_default="0")
    # Optional free-text note explaining the variance.
    note = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
