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

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String

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
    # Optional service-charge percentage applied to the bill (F-061). It is
    # computed OUTSIDE the VAT base — exactly like a tip (POS-13/F-012) — so it
    # never changes the taxable amount or VAT; at settle it resolves to a separate
    # non-taxable line the tenders must also cover. Null/0 = no service charge.
    service_charge_pct = Column(Float, nullable=True, default=0, server_default="0")
    # Serialized JSON map of course -> fire state (e.g. {"starters": "fired"}).
    # Only fired courses are recorded; absent courses are still held (RST-02). A
    # held course can be fired later — the all-day view reads from this + items.
    course_state = Column(String, nullable=True, default="{}", server_default="{}")
    customer_name = Column(String, nullable=True)
    party_size = Column(Integer, nullable=True)
    notes = Column(String, nullable=True)
    opened_at = Column(DateTime(timezone=True), default=datetime.now)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)


class ModifierGroups(Base):
    """A named set of choices that attaches to menu items — F-056 (RST).

    e.g. "Doneness", "Add-ons". ``required`` forces a selection before the line
    can be sent to the kitchen; ``min_select`` / ``max_select`` bound how many
    modifiers in the group may be picked. Owner-scoped like every other entity
    (SEC-02).
    """

    __tablename__ = "modifier_groups"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    name = Column(String, nullable=False)
    name_ar = Column(String, nullable=True)
    required = Column(Boolean, nullable=True, default=False, server_default="false")
    min_select = Column(Integer, nullable=True, default=0, server_default="0")
    max_select = Column(Integer, nullable=True, default=1, server_default="1")
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)


class Modifiers(Base):
    """A single choice within a modifier group — F-056 (RST).

    Carries a bilingual name and a ``price_delta`` (e.g. "extra cheese +5 SAR")
    folded into the line total before VAT. Owner-scoped (SEC-02).
    """

    __tablename__ = "modifiers"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    group_id = Column(Integer, nullable=False, index=True)
    name = Column(String, nullable=False)
    name_ar = Column(String, nullable=True)
    price_delta = Column(Float, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)


class ProductModifierGroups(Base):
    """Link row attaching a modifier group to a product — F-056 (RST).

    When that product is added to a ticket, the attached groups surface (and any
    ``required`` group is enforced). Owner-scoped (SEC-02).
    """

    __tablename__ = "product_modifier_groups"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    product_id = Column(Integer, nullable=False, index=True)
    group_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)


class Combos(Base):
    """A meal bundle sold at a price that overrides the component sum — F-056 (RST).

    ``components`` is a serialized JSON list of ``{"product_id": int, "qty": float}``;
    ``bundle_price`` is the single charge for the whole bundle (it deliberately
    overrides the sum of the components' catalog prices). Owner-scoped (SEC-02).
    """

    __tablename__ = "combos"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    name = Column(String, nullable=False)
    name_ar = Column(String, nullable=True)
    bundle_price = Column(Float, nullable=False, default=0, server_default="0")
    # Serialized JSON list of {"product_id": int, "qty": float}.
    components = Column(String, nullable=True, default="[]", server_default="[]")
    is_active = Column(Boolean, nullable=True, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)


class OrderTicketItems(Base):
    """A single line on an order ticket — the heart of F-055 (RST-02).

    A server adds menu items to an open ticket; each line carries a ``course``
    (starters/mains/dessert), an optional ``seat_no``, a free-text ``note``, a
    serialized ``modifiers`` selection (the modifier model arrives with F-056),
    and a computed ``line_total`` (``qty * unit_price``).

    ``fire_state`` is the line's kitchen lifecycle: ``open`` (still editable on
    the floor) -> ``fired`` (sent to the kitchen, no longer silently deletable)
    -> ``bumped`` (marked done at the station — driven by the KDS slice F-057).
    Every row carries ``user_id`` + ``client_id`` so the service layer scopes
    reads/writes to the owner exactly like every other entity (SEC-02).
    """

    __tablename__ = "order_ticket_items"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    ticket_id = Column(Integer, nullable=False, index=True)
    product_id = Column(Integer, nullable=True, index=True)
    variant_id = Column(Integer, nullable=True)
    name = Column(String, nullable=True)
    qty = Column(Float, nullable=False, default=1, server_default="1")
    unit_price = Column(Float, nullable=False, default=0, server_default="0")
    line_total = Column(Float, nullable=False, default=0, server_default="0")
    course = Column(String, nullable=True, default="mains", server_default="mains")
    seat_no = Column(Integer, nullable=True)
    # open / fired / bumped
    fire_state = Column(String, nullable=True, default="open", server_default="open")
    prep_station_id = Column(Integer, nullable=True)
    notes = Column(String, nullable=True)
    # Serialized modifier selection (F-056 fills this in; stored as JSON text).
    modifiers = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
