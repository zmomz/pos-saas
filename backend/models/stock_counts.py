"""Guided stocktake — sessioned count with freeze → count → variance → approve (M4, #207).

A single ``stock_adjustments`` row is the atomic variance primitive (INV-06): it
snapshots system on-hand, captures the physical count, and posts the delta. A real
stocktake, though, counts a whole branch in one pass and must be *resumable* — a
cashier starts it, freezes the on-hand baseline, walks the shelves scanning
barcodes over a break, reviews the variance, and only then approves. These two
tables are that convenience layer (the one the ``stock_adjustments`` module called
"deferred"):

- ``stock_count_sessions`` is the header — one per stocktake. ``status`` walks
  ``draft → frozen → approved`` (with a terminal ``cancelled``). A draft/frozen
  session is the resumable draft: it persists until approved or cancelled, so the
  flow survives a reload or a shift change.
- ``stock_count_lines`` is one row per product in the count. ``freeze`` snapshots
  every active product's on-hand into ``system_quantity`` (the frozen baseline
  variance is measured against); counting fills ``counted_quantity`` (NULL until a
  shelf is counted); ``variance = counted − system`` is recomputed each count.

Approval posts one ``stock_adjustments`` row per counted line and sets each stock
pool to its counted figure — all in one transaction, so a whole stocktake lands (or
rolls back) atomically. The status flip is gated by a single conditional UPDATE
(like the two-phase transfer receive), so a double-approve never double-posts.

Every row carries ``user_id`` (the merchant's own login account) so the handler
scopes reads/writes to the owner exactly like every other entity — one client can
never see or approve another client's stocktake (SEC-02).
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from core.database import Base


class Stock_count_sessions(Base):
    __tablename__ = "stock_count_sessions"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    # Null branch_id ⇒ a client-level stocktake (counts products.quantity);
    # otherwise the per-branch ledger (product_branch_stock) is counted.
    branch_id = Column(Integer, nullable=True)
    # Optional human label (e.g. "June month-end count").
    name = Column(String, nullable=True)
    # draft → frozen → approved, plus terminal cancelled. A draft/frozen session is
    # the resumable draft.
    status = Column(String, nullable=False, default="draft", server_default="draft")
    note = Column(String, nullable=True)
    # When the on-hand baseline was snapshotted into the lines (freeze).
    frozen_at = Column(DateTime(timezone=True), nullable=True)
    # When the adjustments were posted (approve).
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)


class Stock_count_lines(Base):
    __tablename__ = "stock_count_lines"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    session_id = Column(Integer, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True)
    product_id = Column(Integer, nullable=False)
    # Denormalized name captured at freeze time (the ledger keys off product_id).
    product_name = Column(String, nullable=True)
    # On-hand at freeze — the baseline variance is measured against.
    system_quantity = Column(Integer, nullable=False, default=0, server_default="0")
    # The physical count. NULL until the shelf is counted (an uncounted line posts
    # no adjustment on approve — stock is left untouched, never zeroed).
    counted_quantity = Column(Integer, nullable=True)
    # counted − system (NULL while uncounted).
    variance = Column(Integer, nullable=True)
    note = Column(String, nullable=True)
    counted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
