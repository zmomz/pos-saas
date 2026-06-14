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


class Reservations(Base):
    """A table booked ahead for a future time — ISSUE-069 (RST).

    A host books a ``table`` for a ``reserved_at`` time and a party; the booking
    surfaces on the floor (the table tile shows its next upcoming reservation)
    until it is seated or cancelled. ``status`` is the booking lifecycle:
    ``booked`` (on the books) -> ``seated`` (party arrived, table occupied) /
    ``cancelled`` / ``no_show``. Owner-scoped like every other entity (SEC-02).
    """

    __tablename__ = "reservations"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    branch_id = Column(Integer, nullable=True)
    table_id = Column(Integer, nullable=True, index=True)
    customer_name = Column(String, nullable=True)
    party_size = Column(Integer, nullable=True)
    reserved_at = Column(DateTime(timezone=True), nullable=False)
    # booked / seated / cancelled / no_show
    status = Column(String, nullable=True, default="booked", server_default="booked")
    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)


class WaitlistEntries(Base):
    """A walk-in party queued for the next free table — ISSUE-069 (RST).

    A host adds a party to the queue; entries surface in arrival order. Seating
    an entry to a table flips it ``waiting -> seated``, opens an order ticket on
    that table, and records ``seated_table_id`` / ``seated_ticket_id``. ``status``
    is ``waiting`` (in the queue) -> ``seated`` / ``cancelled``. Owner-scoped
    like every other entity (SEC-02).
    """

    __tablename__ = "waitlist_entries"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    branch_id = Column(Integer, nullable=True)
    customer_name = Column(String, nullable=True)
    party_size = Column(Integer, nullable=True)
    # waiting / seated / cancelled
    status = Column(String, nullable=True, default="waiting", server_default="waiting")
    notes = Column(String, nullable=True)
    seated_table_id = Column(Integer, nullable=True)
    seated_ticket_id = Column(Integer, nullable=True)
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


class BillOfMaterials(Base):
    """A recipe/BOM row: a component consumed when a parent product sells — F-062 (RST).

    An inventory manager defines a parent product's bill of materials as a set of
    ``component_product_id`` rows each carrying a ``qty_per`` (how much of the
    component one unit of the parent consumes). When a BOM-backed line is sold the
    parent expands into ``qty_per × qty_sold`` deductions of each component — inside
    the same atomic stock transaction as the sale, so a failed sale never leaves a
    partial component deduction. Component ``cost_price`` rolls up to a true
    cost-of-goods value on the parent (the hook consumed later by margin reporting,
    F-068). Owner-scoped like every other entity (SEC-02).
    """

    __tablename__ = "bill_of_materials"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    parent_product_id = Column(Integer, nullable=False, index=True)
    component_product_id = Column(Integer, nullable=False, index=True)
    # How much of the component one unit of the parent consumes (e.g. 0.2 kg of
    # beef per burger). A Float so recipes can express fractional quantities.
    qty_per = Column(Float, nullable=False, default=1, server_default="1")
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)


class PrepStations(Base):
    """A kitchen prep-station a fired item routes to — F-057 (RST).

    A menu manager defines the stations that prepare food (e.g. Grill, Bar,
    Cold). Each menu line carries an optional ``prep_station_id``
    (``order_ticket_items.prep_station_id``); when a course is fired the fired
    lines fan out to the station that prepares them and materialize as
    ``kds_tickets`` on that station's Kitchen-Display column. Carries a bilingual
    name so the board and the printed KOT render in Arabic. Owner-scoped like
    every other entity (SEC-02).
    """

    __tablename__ = "prep_stations"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    name = Column(String, nullable=False)
    name_ar = Column(String, nullable=True)
    # Lower sorts first on the board (defaults to creation order otherwise).
    sort_order = Column(Integer, nullable=True, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)


class KdsTickets(Base):
    """A materialized kitchen card — the fired items of one course routed to one
    station — F-057 (RST).

    When a server fires a course (F-055) the fired lines are grouped by their
    ``prep_station_id`` and one ``kds_ticket`` is minted per station, snapshotting
    just enough to render the Kitchen-Display card and the 80mm KOT without
    re-joining: ``items_json`` is the rendered line snapshot (name, qty, notes,
    modifier names — **never a price**, a KOT carries no money) and ``item_ids``
    is the list of source ``order_ticket_items`` ids so a bump/recall can keep the
    line's ``fire_state`` in sync with the card.

    ``status`` is the card's lifecycle: ``active`` (on the board, cooking) ->
    ``bumped`` (completed, cleared from the active board). A recall flips it back
    to ``active``. ``fired_at`` drives the on-card timer; ``bumped_at`` stamps the
    completion. Owner-scoped (SEC-02).
    """

    __tablename__ = "kds_tickets"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    order_ticket_id = Column(Integer, nullable=False, index=True)
    table_id = Column(Integer, nullable=True)
    # The prep-station this card routes to (None = unrouted / expo column).
    station_id = Column(Integer, nullable=True, index=True)
    course = Column(String, nullable=True)
    # active / bumped
    status = Column(String, nullable=True, default="active", server_default="active")
    # Serialized JSON list of source order_ticket_item ids (line-state sync).
    item_ids = Column(String, nullable=True, default="[]", server_default="[]")
    # Serialized JSON render snapshot: [{name, name_ar, qty, notes, modifiers}].
    items_json = Column(String, nullable=True, default="[]", server_default="[]")
    customer_name = Column(String, nullable=True)
    order_type = Column(String, nullable=True)
    fired_at = Column(DateTime(timezone=True), default=datetime.now)
    bumped_at = Column(DateTime(timezone=True), nullable=True)
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
    # A combo/bundle line carries combo_id (and product_id is None); at settle the
    # line expands into its component products so stock deducts (F-056 / ISSUE-032).
    combo_id = Column(Integer, nullable=True, index=True)
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
    # Set when a prior partial settlement (ISSUE-070) already billed this line into
    # its own fiscal invoice. NULL = still on the unpaid remainder; the check/split/
    # settle paths only ever see unpaid lines, so a line is never billed twice.
    settled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
