"""Restaurant operations — floor map, tables, and order tickets (RST-01..03, F-045).

The first slice of the restaurant vertical (CLAUDE.md "unified retail + restaurant").
A merchant whose ``clients.business_type`` is ``restaurant`` or ``both`` can map a
floor (``floor_zones``), place ``restaurant_tables`` with seat counts, and open an
``order_ticket`` against a table — flipping it from ``free`` to ``occupied``. The
heavier kitchen surface (KDS/KOT fire, modifiers/combos, settle-to-invoice) is a
deliberate follow-up; these three tables are the foundation the rest builds on.

Every row carries ``user_id`` (the merchant's own login account) so the service
layer scopes reads/writes to the owner exactly like every other entity (SEC-02).

States (mirrors INTENDED_BEHAVIOR.md §3.5 / the state-machine catalog):
* table ``state``        : free / occupied / bill_printed
* order ticket ``status``: open / held / fired / settled / void
* order ``order_type``   : dine_in / takeaway / delivery
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from core.database import Base


class FloorZones(Base):
    """A named area of a branch's floor (e.g. "Main Hall", "Terrace") — RST-01."""

    __tablename__ = "floor_zones"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    branch_id = Column(Integer, nullable=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)


class RestaurantTables(Base):
    """A seatable table on the floor map — RST-01.

    ``state`` drives the floor-map tile colour: ``free`` (seatable), ``occupied``
    (an order ticket is open against it), ``bill_printed`` (check printed, awaiting
    settlement). ``current_ticket_id`` links the open ticket while occupied.
    """

    __tablename__ = "restaurant_tables"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    branch_id = Column(Integer, nullable=True)
    zone_id = Column(Integer, nullable=True, index=True)
    name = Column(String, nullable=False)
    seats = Column(Integer, nullable=True, default=4, server_default="4")
    # free / occupied / bill_printed
    state = Column(String, nullable=True, default="free", server_default="free")
    current_ticket_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)


class OrderTickets(Base):
    """An open restaurant order against a table (or takeaway/delivery) — RST-02/03.

    Created when a server opens a table; settling it into a ZATCA invoice via the
    POS atomic path is a follow-up slice, so for now it carries the lifecycle state
    and the table linkage only.
    """

    __tablename__ = "order_tickets"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    branch_id = Column(Integer, nullable=True)
    table_id = Column(Integer, nullable=True, index=True)
    # dine_in / takeaway / delivery
    order_type = Column(String, nullable=True, default="dine_in", server_default="dine_in")
    # open / held / fired / settled / void
    status = Column(String, nullable=True, default="open", server_default="open")
    customer_name = Column(String, nullable=True)
    party_size = Column(Integer, nullable=True)
    notes = Column(String, nullable=True)
    opened_at = Column(DateTime(timezone=True), default=datetime.now)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
