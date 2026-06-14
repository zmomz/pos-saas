"""Inter-branch stock transfers (INV-05, F-032).

The Branch Management screen has always shown a "Transfer Stock" dialog, but it
POSTed to ``/api/v1/production/branches/transfer`` — a route that did not exist,
so the action 404'd (a dead-end UI). This is the audit record for a completed
inter-branch move: stock is decremented from ``from_branch_id`` and incremented at
``to_branch_id`` on the per-branch ledger (``product_branch_stock``) atomically, and
one of these rows is written so the movement is traceable.

Every row carries ``user_id`` (the merchant's own login account) so the service
layer scopes reads/writes to the owner exactly like every other entity — one client
can never move another client's stock (SEC-02).

``status`` follows the IB §inventory state line ``draft / sent / received``; the
one-step transfer the UI performs lands directly in ``received`` (stock already
moved). The two-phase send→receive wizard (INV-05 vision) can reuse the earlier
states later without a schema change.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from core.database import Base


class Stock_transfers(Base):
    __tablename__ = "stock_transfers"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    from_branch_id = Column(Integer, nullable=False)
    to_branch_id = Column(Integer, nullable=False)
    product_id = Column(Integer, nullable=False)
    # Denormalized name captured at transfer time (the ledger keys off product_id).
    product_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False, default=0, server_default="0")
    # draft / in_transit / received. A one-step transfer lands directly in
    # ``received``; a two-phase transfer (#61) sits in ``in_transit`` between
    # dispatch and receive.
    status = Column(String, nullable=False, default="received", server_default="received")
    # Two-phase transfer (#61): the quantity actually booked in at the destination
    # on receive, and the dispatched−received shortfall (in-transit shrink). Null
    # until a two-phase transfer is received; a one-step transfer leaves them null.
    received_quantity = Column(Integer, nullable=True)
    discrepancy = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
