"""Service layer for restaurant floor/table/order-ticket operations (F-045).

All operations are scoped to ``user_id`` (the merchant's own account) so one
client can never read or mutate another client's floor — the same ownership
invariant the generic entity triad enforces (SEC-02). State transitions
(opening an order, freeing a table) are committed atomically.
"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.products import Products
from models.restaurant import (
    BillOfMaterials,
    Combos,
    FloorZones,
    KdsTickets,
    Modifiers,
    ModifierGroups,
    OrderTicketItems,
    OrderTickets,
    PrepStations,
    ProductModifierGroups,
    Reservations,
    RestaurantTables,
    WaitlistEntries,
)
from services.kds_channel import kds_broker

logger = logging.getLogger(__name__)

# Allowed enum values (mirrors models.restaurant docstring).
TABLE_STATES = ("free", "occupied", "bill_printed")
ORDER_TYPES = ("dine_in", "takeaway", "delivery")
TICKET_STATUSES = ("open", "held", "fired", "settled", "void")
# A line's kitchen lifecycle (OrderTicketItems.fire_state). ``bumped`` is reached
# at the station by the KDS slice (F-057); here lines go open -> fired.
ITEM_FIRE_STATES = ("open", "fired", "bumped")
# How a bill can be divided (F-055 split).
SPLIT_STRATEGIES = ("seat", "amount", "item")
# A KDS card's lifecycle (F-057): active (on the board) -> bumped (completed).
KDS_STATUSES = ("active", "bumped")
# Statuses past which a ticket can no longer be edited from the floor.
CLOSED_TICKET_STATUSES = ("settled", "void")
# A reservation's lifecycle (ISSUE-069): booked -> seated / cancelled / no_show.
RESERVATION_STATUSES = ("booked", "seated", "cancelled", "no_show")
# A waitlist entry's lifecycle (ISSUE-069): waiting -> seated / cancelled.
WAITLIST_STATUSES = ("waiting", "seated", "cancelled")

# Print routing per order type (F-058). ``order_type`` stops being a dead label
# and decides where the order's documents print: the kitchen always gets a KOT,
# but the customer-facing copy differs — a dine-in table gets a table check, a
# takeaway gets a counter label + receipt, a delivery gets a delivery docket +
# receipt. The KDS station fan-out within the kitchen is F-057; this is the
# coarser order-type-level routing the floor and the later aggregator slice rely
# on. Each value is the ordered list of print targets.
PRINT_ROUTING = {
    "dine_in": ["kitchen", "table_check"],
    "takeaway": ["kitchen", "takeaway_label", "customer_receipt"],
    "delivery": ["kitchen", "delivery_docket", "customer_receipt"],
}


class SettleLine(BaseModel):
    """One normalized cart line the sale core mints a fiscal sale from (F-059).

    A ticket line (with its modifiers already folded into ``line_total``) becomes
    one of these. ``product_id`` is optional so a combo/ad-hoc line (no catalog
    product) still settles — the sale core skips inventory for an unknown product
    and the authoritative subtotal/VAT/total carried on the ``NormalizedCart`` (not
    the per-line figures) drive the stamped invoice. Exposes ``model_dump()`` plus
    ``product_id`` / ``quantity`` / ``variant_id`` — the contract ``execute_sale``
    expects of a cart line.
    """

    product_id: Optional[int] = None
    variant_id: Optional[int] = None
    name: Optional[str] = None
    name_ar: Optional[str] = None
    price: float = 0.0
    quantity: float = 1.0
    discount: float = 0.0
    modifiers: Optional[str] = None


class RestaurantService:
    """Floor zones, tables, and order tickets for a single client merchant."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------ zones
    async def list_zones(self, user_id: str) -> List[FloorZones]:
        result = await self.db.execute(
            select(FloorZones)
            .where(FloorZones.user_id == user_id)
            .order_by(FloorZones.id.asc())
        )
        return result.scalars().all()

    async def create_zone(self, data: Dict[str, Any], user_id: str, client_id: Optional[int]) -> FloorZones:
        try:
            zone = FloorZones(
                user_id=user_id,
                client_id=client_id,
                branch_id=data.get("branch_id"),
                name=data["name"],
            )
            self.db.add(zone)
            await self.db.commit()
            await self.db.refresh(zone)
            logger.info(f"Created floor zone {zone.id} for user {user_id}")
            return zone
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating floor zone: {str(e)}")
            raise

    async def get_zone(self, zone_id: int, user_id: str) -> Optional[FloorZones]:
        result = await self.db.execute(
            select(FloorZones).where(FloorZones.id == zone_id, FloorZones.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def update_zone(self, zone_id: int, updates: Dict[str, Any], user_id: str) -> Optional[FloorZones]:
        zone = await self.get_zone(zone_id, user_id)
        if not zone:
            return None
        try:
            for key, value in updates.items():
                if hasattr(zone, key) and key not in ("id", "user_id", "client_id"):
                    setattr(zone, key, value)
            await self.db.commit()
            await self.db.refresh(zone)
            return zone
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating floor zone {zone_id}: {str(e)}")
            raise

    async def delete_zone(self, zone_id: int, user_id: str) -> bool:
        zone = await self.get_zone(zone_id, user_id)
        if not zone:
            return False
        try:
            await self.db.delete(zone)
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting floor zone {zone_id}: {str(e)}")
            raise

    # ----------------------------------------------------------------- tables
    async def list_tables(
        self,
        user_id: str,
        zone_id: Optional[int] = None,
        branch_id: Optional[int] = None,
        state: Optional[str] = None,
    ) -> List[RestaurantTables]:
        query = select(RestaurantTables).where(RestaurantTables.user_id == user_id)
        if zone_id is not None:
            query = query.where(RestaurantTables.zone_id == zone_id)
        if branch_id is not None:
            query = query.where(RestaurantTables.branch_id == branch_id)
        if state is not None:
            query = query.where(RestaurantTables.state == state)
        query = query.order_by(RestaurantTables.id.asc())
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_table(self, table_id: int, user_id: str) -> Optional[RestaurantTables]:
        result = await self.db.execute(
            select(RestaurantTables).where(
                RestaurantTables.id == table_id, RestaurantTables.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def create_table(self, data: Dict[str, Any], user_id: str, client_id: Optional[int]) -> RestaurantTables:
        try:
            table = RestaurantTables(
                user_id=user_id,
                client_id=client_id,
                branch_id=data.get("branch_id"),
                zone_id=data.get("zone_id"),
                name=data["name"],
                seats=data.get("seats") if data.get("seats") is not None else 4,
                state="free",
            )
            self.db.add(table)
            await self.db.commit()
            await self.db.refresh(table)
            logger.info(f"Created restaurant table {table.id} for user {user_id}")
            return table
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating restaurant table: {str(e)}")
            raise

    async def update_table(self, table_id: int, updates: Dict[str, Any], user_id: str) -> Optional[RestaurantTables]:
        table = await self.get_table(table_id, user_id)
        if not table:
            return None
        try:
            for key, value in updates.items():
                if hasattr(table, key) and key not in ("id", "user_id", "client_id", "current_ticket_id"):
                    setattr(table, key, value)
            await self.db.commit()
            await self.db.refresh(table)
            return table
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating restaurant table {table_id}: {str(e)}")
            raise

    async def delete_table(self, table_id: int, user_id: str) -> bool:
        table = await self.get_table(table_id, user_id)
        if not table:
            return False
        try:
            await self.db.delete(table)
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting restaurant table {table_id}: {str(e)}")
            raise

    # ----------------------------------------------------------- reservations
    @staticmethod
    def _parse_reserved_at(value: Any) -> datetime:
        """Coerce the request's ``reserved_at`` into a datetime (ISO-8601)."""
        if isinstance(value, datetime):
            return value
        if not value:
            raise ValueError("reserved_at is required")
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("reserved_at must be an ISO-8601 datetime")

    async def list_reservations(
        self,
        user_id: str,
        status: Optional[str] = None,
        table_id: Optional[int] = None,
    ) -> List[Reservations]:
        query = select(Reservations).where(Reservations.user_id == user_id)
        if status is not None:
            query = query.where(Reservations.status == status)
        if table_id is not None:
            query = query.where(Reservations.table_id == table_id)
        # Soonest bookings first — the order a host reads the floor in.
        query = query.order_by(Reservations.reserved_at.asc())
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_reservation(self, reservation_id: int, user_id: str) -> Optional[Reservations]:
        result = await self.db.execute(
            select(Reservations).where(
                Reservations.id == reservation_id, Reservations.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def create_reservation(
        self, data: Dict[str, Any], user_id: str, client_id: Optional[int]
    ) -> Reservations:
        """Book a table ahead for a future time (ISSUE-069).

        Raises ``ValueError`` if ``reserved_at`` is missing/unparseable or the
        referenced table isn't the caller's (so one client can't book onto
        another's floor, SEC-02).
        """
        reserved_at = self._parse_reserved_at(data.get("reserved_at"))
        table_id = data.get("table_id")
        branch_id = data.get("branch_id")
        if table_id is not None:
            table = await self.get_table(table_id, user_id)
            if not table:
                raise ValueError("Table not found")
            if branch_id is None:
                branch_id = table.branch_id
        try:
            reservation = Reservations(
                user_id=user_id,
                client_id=client_id,
                branch_id=branch_id,
                table_id=table_id,
                customer_name=data.get("customer_name"),
                party_size=data.get("party_size"),
                reserved_at=reserved_at,
                status="booked",
                notes=data.get("notes"),
            )
            self.db.add(reservation)
            await self.db.commit()
            await self.db.refresh(reservation)
            logger.info(f"Created reservation {reservation.id} for user {user_id}")
            return reservation
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating reservation: {str(e)}")
            raise

    async def update_reservation(
        self, reservation_id: int, updates: Dict[str, Any], user_id: str
    ) -> Optional[Reservations]:
        reservation = await self.get_reservation(reservation_id, user_id)
        if not reservation:
            return None
        if "reserved_at" in updates and updates["reserved_at"] is not None:
            updates["reserved_at"] = self._parse_reserved_at(updates["reserved_at"])
        if "status" in updates and updates["status"] not in RESERVATION_STATUSES:
            raise ValueError(
                f"Invalid status. Allowed: {', '.join(RESERVATION_STATUSES)}"
            )
        try:
            for key, value in updates.items():
                if hasattr(reservation, key) and key not in ("id", "user_id", "client_id"):
                    setattr(reservation, key, value)
            await self.db.commit()
            await self.db.refresh(reservation)
            return reservation
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating reservation {reservation_id}: {str(e)}")
            raise

    async def cancel_reservation(self, reservation_id: int, user_id: str) -> Optional[Reservations]:
        """Mark a reservation cancelled (the booking lifecycle, ISSUE-069)."""
        return await self.update_reservation(reservation_id, {"status": "cancelled"}, user_id)

    async def next_reservation_for_table(
        self, table_id: int, user_id: str
    ) -> Optional[Reservations]:
        """The soonest still-booked reservation for a table — the floor overlay."""
        result = await self.db.execute(
            select(Reservations)
            .where(
                Reservations.user_id == user_id,
                Reservations.table_id == table_id,
                Reservations.status == "booked",
            )
            .order_by(Reservations.reserved_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    # -------------------------------------------------------------- waitlist
    async def list_waitlist(
        self, user_id: str, status: Optional[str] = "waiting"
    ) -> List[WaitlistEntries]:
        query = select(WaitlistEntries).where(WaitlistEntries.user_id == user_id)
        if status is not None:
            query = query.where(WaitlistEntries.status == status)
        # FIFO — earliest arrival is next to be seated.
        query = query.order_by(WaitlistEntries.id.asc())
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_waitlist_entry(self, entry_id: int, user_id: str) -> Optional[WaitlistEntries]:
        result = await self.db.execute(
            select(WaitlistEntries).where(
                WaitlistEntries.id == entry_id, WaitlistEntries.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def add_to_waitlist(
        self, data: Dict[str, Any], user_id: str, client_id: Optional[int]
    ) -> WaitlistEntries:
        """Queue a walk-in party (ISSUE-069)."""
        try:
            entry = WaitlistEntries(
                user_id=user_id,
                client_id=client_id,
                branch_id=data.get("branch_id"),
                customer_name=data.get("customer_name"),
                party_size=data.get("party_size"),
                status="waiting",
                notes=data.get("notes"),
            )
            self.db.add(entry)
            await self.db.commit()
            await self.db.refresh(entry)
            logger.info(f"Added waitlist entry {entry.id} for user {user_id}")
            return entry
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error adding waitlist entry: {str(e)}")
            raise

    async def cancel_waitlist_entry(self, entry_id: int, user_id: str) -> Optional[WaitlistEntries]:
        entry = await self.get_waitlist_entry(entry_id, user_id)
        if not entry:
            return None
        try:
            entry.status = "cancelled"
            await self.db.commit()
            await self.db.refresh(entry)
            return entry
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error cancelling waitlist entry {entry_id}: {str(e)}")
            raise

    async def seat_waitlist_entry(
        self, entry_id: int, table_id: int, user_id: str, client_id: Optional[int]
    ) -> Optional[Dict[str, Any]]:
        """Seat a queued party to a table, opening an order ticket (ISSUE-069).

        Atomic: the entry flips ``waiting -> seated`` and an ``open`` dine-in
        ticket is opened on the free table (which itself flips to ``occupied``),
        committing together. Raises ``ValueError`` if the entry is already
        seated/cancelled or the table is occupied; returns ``None`` (caller →
        404) if the entry or table isn't the caller's.
        """
        entry = await self.get_waitlist_entry(entry_id, user_id)
        if not entry:
            return None
        if entry.status != "waiting":
            raise ValueError(f"Waitlist entry is already {entry.status}")
        table = await self.get_table(table_id, user_id)
        if not table:
            return None
        # open_order enforces the free->occupied invariant and raises if occupied.
        ticket = await self.open_order(
            table_id,
            {
                "order_type": "dine_in",
                "customer_name": entry.customer_name,
                "party_size": entry.party_size,
            },
            user_id,
            client_id,
        )
        try:
            entry.status = "seated"
            entry.seated_table_id = table_id
            entry.seated_ticket_id = ticket.id
            await self.db.commit()
            await self.db.refresh(entry)
            logger.info(f"Seated waitlist entry {entry.id} to table {table_id} (ticket {ticket.id})")
            return {"entry": entry, "ticket": ticket}
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error seating waitlist entry {entry_id}: {str(e)}")
            raise

    # ---------------------------------------------------------- order tickets
    async def open_order(
        self,
        table_id: int,
        data: Dict[str, Any],
        user_id: str,
        client_id: Optional[int],
    ) -> OrderTickets:
        """Open an order ticket against a free table, marking it occupied (RST-02/03).

        Atomic: the new ``open`` ticket and the table's ``free -> occupied`` flip
        commit together. Raises ``ValueError`` if the table already has an open
        order so a second server can't double-seat it.
        """
        table = await self.get_table(table_id, user_id)
        if not table:
            return None  # caller maps to 404
        if table.state == "occupied":
            raise ValueError("Table already has an open order")
        try:
            ticket = OrderTickets(
                user_id=user_id,
                client_id=client_id,
                branch_id=table.branch_id,
                table_id=table.id,
                order_type=data.get("order_type") or "dine_in",
                status="open",
                customer_name=data.get("customer_name"),
                party_size=data.get("party_size"),
                notes=data.get("notes"),
            )
            self.db.add(ticket)
            await self.db.flush()  # assign ticket.id before linking it to the table

            table.state = "occupied"
            table.current_ticket_id = ticket.id

            await self.db.commit()
            await self.db.refresh(ticket)
            logger.info(f"Opened order ticket {ticket.id} on table {table.id}")
            return ticket
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error opening order on table {table_id}: {str(e)}")
            raise

    async def create_ticket(
        self,
        data: Dict[str, Any],
        user_id: str,
        client_id: Optional[int],
    ) -> Optional[OrderTickets]:
        """Open an order ticket whose flow is driven by ``order_type`` (F-058).

        * ``dine_in`` still requires a table — it delegates to ``open_order`` so
          the table flips ``free -> occupied`` exactly as before (existing
          behavior preserved). Raises ``ValueError`` if no table is supplied.
        * ``takeaway`` / ``delivery`` are **tableless** — the ticket is created
          with ``table_id = None`` and no floor table is touched. This is the
          path the aggregator-ingest slice (F-060) later builds on.

        Returns the ticket, ``None`` if a dine-in table isn't found (caller maps
        to 404), or raises ``ValueError`` (caller maps to 400/409).
        """
        order_type = data.get("order_type") or "dine_in"
        if order_type == "dine_in":
            table_id = data.get("table_id")
            if table_id is None:
                raise ValueError("A dine-in order requires a table")
            return await self.open_order(table_id, data, user_id, client_id)

        # Tableless takeaway / delivery — no floor table required (F-058).
        try:
            ticket = OrderTickets(
                user_id=user_id,
                client_id=client_id,
                branch_id=data.get("branch_id"),
                table_id=None,
                order_type=order_type,
                status="open",
                customer_name=data.get("customer_name"),
                party_size=data.get("party_size"),
                notes=data.get("notes"),
            )
            self.db.add(ticket)
            await self.db.commit()
            await self.db.refresh(ticket)
            logger.info(f"Opened tableless {order_type} ticket {ticket.id} for user {user_id}")
            return ticket
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating {order_type} ticket: {str(e)}")
            raise

    @staticmethod
    def print_routing(ticket: OrderTickets) -> Dict[str, Any]:
        """Where a ticket's documents print, driven by ``order_type`` (F-058).

        Returns ``{ticket_id, order_type, targets}`` where ``targets`` is the
        ordered list of print destinations for that order type (see
        ``PRINT_ROUTING``). Dine-in / takeaway / delivery route differently.
        """
        order_type = ticket.order_type or "dine_in"
        targets = PRINT_ROUTING.get(order_type, PRINT_ROUTING["dine_in"])
        return {
            "ticket_id": ticket.id,
            "order_type": order_type,
            "targets": list(targets),
        }

    async def list_tickets(
        self,
        user_id: str,
        status: Optional[str] = None,
        table_id: Optional[int] = None,
    ) -> List[OrderTickets]:
        query = select(OrderTickets).where(OrderTickets.user_id == user_id)
        if status is not None:
            query = query.where(OrderTickets.status == status)
        if table_id is not None:
            query = query.where(OrderTickets.table_id == table_id)
        query = query.order_by(OrderTickets.id.desc())
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_ticket(self, ticket_id: int, user_id: str) -> Optional[OrderTickets]:
        result = await self.db.execute(
            select(OrderTickets).where(
                OrderTickets.id == ticket_id, OrderTickets.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def count_tables(self, user_id: str) -> int:
        result = await self.db.execute(
            select(func.count(RestaurantTables.id)).where(RestaurantTables.user_id == user_id)
        )
        return result.scalar() or 0

    # ------------------------------------------------------ order ticket items
    async def list_items(self, ticket_id: int, user_id: str) -> List[OrderTicketItems]:
        """Lines on a ticket the caller owns (owner-scoped, SEC-02)."""
        result = await self.db.execute(
            select(OrderTicketItems)
            .where(
                OrderTicketItems.ticket_id == ticket_id,
                OrderTicketItems.user_id == user_id,
            )
            .order_by(OrderTicketItems.id.asc())
        )
        return result.scalars().all()

    async def _unsettled_items(
        self, ticket_id: int, user_id: str
    ) -> List[OrderTicketItems]:
        """The ticket's unpaid remainder — lines no prior partial settlement billed.

        A partial settlement (ISSUE-070) stamps the lines it invoices with
        ``settled_at``; everything that still bills (check, split, full settle) reads
        the remainder through here so a paid line is never charged twice.
        """
        return [
            i for i in await self.list_items(ticket_id, user_id) if i.settled_at is None
        ]

    async def get_item(self, item_id: int, user_id: str) -> Optional[OrderTicketItems]:
        result = await self.db.execute(
            select(OrderTicketItems).where(
                OrderTicketItems.id == item_id, OrderTicketItems.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def add_item(
        self,
        ticket_id: int,
        data: Dict[str, Any],
        user_id: str,
        client_id: Optional[int],
    ) -> Optional[OrderTicketItems]:
        """Add a menu item to an open ticket (RST-02).

        Returns ``None`` if the ticket isn't found (caller maps to 404). Raises
        ``ValueError`` if the ticket is already settled/void. ``unit_price``
        defaults to the product's catalog price when omitted; ``line_total`` is
        always computed server-side (``qty * unit_price``).
        """
        ticket = await self.get_ticket(ticket_id, user_id)
        if not ticket:
            return None
        if (ticket.status or "open") in CLOSED_TICKET_STATUSES:
            raise ValueError("Cannot add items to a settled or voided ticket")

        qty = data.get("qty")
        qty = float(qty) if qty is not None else 1.0
        if qty <= 0:
            raise ValueError("Quantity must be greater than zero")

        product = None
        product_id = data.get("product_id")
        if product_id is not None:
            product = await self._owned_product(product_id, user_id)
            if product is None:
                raise ValueError("Product not found")

        # A combo prices the line at its bundle price — overriding the component
        # sum (F-056). It can't be combined with a standalone product on one line.
        combo = None
        combo_id = data.get("combo_id")
        if combo_id is not None:
            combo = await self.get_combo(combo_id, user_id)
            if combo is None:
                raise ValueError("Combo not found")

        unit_price = data.get("unit_price")
        if unit_price is None:
            if combo is not None:
                unit_price = float(combo.bundle_price)
            elif product is not None:
                unit_price = float(product.price)
            else:
                unit_price = 0.0
        unit_price = round(float(unit_price), 2)

        name = (
            data.get("name")
            or (combo.name if combo is not None else None)
            or (product.name if product is not None else None)
        )

        # Resolve the selected modifiers: enforce required groups, sum the price
        # deltas (added once per line, before VAT — the line-math contract), and
        # persist the serialized selection so the kitchen makes it as ordered.
        modifier_total, modifiers = await self._resolve_modifiers(
            data.get("modifiers"), product_id, user_id
        )

        try:
            item = OrderTicketItems(
                user_id=user_id,
                client_id=client_id,
                ticket_id=ticket.id,
                product_id=product_id,
                combo_id=combo_id,
                variant_id=data.get("variant_id"),
                name=name,
                qty=qty,
                unit_price=unit_price,
                line_total=round(qty * unit_price + modifier_total, 2),
                course=data.get("course") or "mains",
                seat_no=data.get("seat_no"),
                fire_state="open",
                prep_station_id=data.get("prep_station_id"),
                notes=data.get("notes"),
                modifiers=modifiers,
            )
            self.db.add(item)
            await self.db.commit()
            await self.db.refresh(item)
            logger.info(f"Added line {item.id} to ticket {ticket.id}")
            return item
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error adding line to ticket {ticket_id}: {str(e)}")
            raise

    async def update_item(
        self,
        ticket_id: int,
        item_id: int,
        updates: Dict[str, Any],
        user_id: str,
    ) -> Optional[OrderTicketItems]:
        """Edit an *open* line's qty/course/seat/notes (RST-02).

        Raises ``ValueError`` if the line has already been fired — a fired line
        can't be silently re-priced on the floor.
        """
        item = await self.get_item(item_id, user_id)
        if not item or item.ticket_id != ticket_id:
            return None
        if (item.fire_state or "open") != "open":
            raise ValueError("Cannot edit a fired line")
        try:
            editable = ("qty", "course", "seat_no", "notes", "unit_price", "name")
            for key, value in updates.items():
                if key in editable and hasattr(item, key):
                    setattr(item, key, value)
            item.qty = float(item.qty or 0)
            item.unit_price = round(float(item.unit_price or 0), 2)
            # Keep the (qty-independent) modifier deltas folded into the line total.
            item.line_total = round(
                item.qty * item.unit_price + self._modifier_total(item.modifiers), 2
            )
            await self.db.commit()
            await self.db.refresh(item)
            return item
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating line {item_id}: {str(e)}")
            raise

    async def void_item(self, ticket_id: int, item_id: int, user_id: str) -> Optional[bool]:
        """Remove an *open* line. Returns ``None`` if not found.

        Raises ``ValueError`` if the line was already fired — a fired line can't
        be silently deleted (it has gone to the kitchen); it must be voided
        through a tracked path, not a plain delete.
        """
        item = await self.get_item(item_id, user_id)
        if not item or item.ticket_id != ticket_id:
            return None
        if (item.fire_state or "open") != "open":
            raise ValueError("Cannot delete a fired line")
        try:
            await self.db.delete(item)
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error voiding line {item_id}: {str(e)}")
            raise

    async def fire_course(
        self, ticket_id: int, course: str, user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Fire one course to the kitchen (RST-02).

        Advances every ``open`` line of that course to ``fired``, records the
        course in the ticket's ``course_state`` map, and moves the ticket status
        to ``fired``. Other courses stay held and can be fired later. Returns a
        summary dict, or ``None`` if the ticket isn't found.
        """
        ticket = await self.get_ticket(ticket_id, user_id)
        if not ticket:
            return None
        if (ticket.status or "open") in CLOSED_TICKET_STATUSES:
            raise ValueError("Cannot fire a settled or voided ticket")
        items = await self.list_items(ticket_id, user_id)
        target = [i for i in items if (i.course or "mains") == course and (i.fire_state or "open") == "open"]
        try:
            for line in target:
                line.fire_state = "fired"
            cs = self._load_course_state(ticket)
            cs[course] = "fired"
            ticket.course_state = json.dumps(cs)
            ticket.status = "fired"
            # F-057: materialize the fired lines onto the Kitchen Display — one
            # card per prep-station — in the SAME transaction as the fire, so the
            # board and the server's screen can never disagree on fired state.
            kds_cards = self._materialize_kds_for_fire(ticket, course, target, user_id)
            await self.db.commit()
            fired_ids = [line.id for line in target]
            # Push the new cards to any open kitchen stream (≤1s real-time, F-057).
            for card in kds_cards:
                await self.db.refresh(card)
                kds_broker.publish(
                    user_id, {"type": "fired", "card": self._kds_to_dict(card)}
                )
            logger.info(
                f"Fired course '{course}' on ticket {ticket_id}: {len(fired_ids)} line(s), "
                f"{len(kds_cards)} KDS card(s)"
            )
            return {
                "ticket_id": ticket_id,
                "course": course,
                "fired_item_ids": fired_ids,
                "fired_count": len(fired_ids),
                "kds_ticket_ids": [c.id for c in kds_cards],
            }
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error firing course '{course}' on ticket {ticket_id}: {str(e)}")
            raise

    async def transfer_ticket(
        self, ticket_id: int, target_table_id: int, user_id: str
    ) -> Optional[OrderTickets]:
        """Move a ticket (and its lines, which follow by ``ticket_id``) to another
        table (RST-02). The source table frees, the target occupies.

        Raises ``ValueError`` if the target is missing or already occupied.
        Returns ``None`` if the ticket isn't found.
        """
        ticket = await self.get_ticket(ticket_id, user_id)
        if not ticket:
            return None
        target = await self.get_table(target_table_id, user_id)
        if target is None:
            raise ValueError("Target table not found")
        if target.id == ticket.table_id:
            return ticket  # no-op transfer onto the same table
        if (target.state or "free") == "occupied":
            raise ValueError("Target table already has an open order")
        try:
            # Free the source table if it still points at this ticket.
            if ticket.table_id is not None:
                source = await self.get_table(ticket.table_id, user_id)
                if source is not None and source.current_ticket_id == ticket.id:
                    source.state = "free"
                    source.current_ticket_id = None
            # Occupy the target.
            target.state = "occupied"
            target.current_ticket_id = ticket.id
            ticket.table_id = target.id
            await self.db.commit()
            await self.db.refresh(ticket)
            logger.info(f"Transferred ticket {ticket_id} to table {target_table_id}")
            return ticket
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error transferring ticket {ticket_id}: {str(e)}")
            raise

    async def merge_tickets(
        self, target_ticket_id: int, source_ticket_id: int, user_id: str
    ) -> Optional[OrderTickets]:
        """Merge ``source`` into ``target`` so they share one bill (RST-02).

        Every source line is re-pointed at the target ticket, the source ticket
        is voided, and the source's table frees. Returns the target ticket, or
        ``None`` if either ticket isn't found.
        """
        if target_ticket_id == source_ticket_id:
            raise ValueError("Cannot merge a ticket into itself")
        target = await self.get_ticket(target_ticket_id, user_id)
        source = await self.get_ticket(source_ticket_id, user_id)
        if not target or not source:
            return None
        if (target.status or "open") in CLOSED_TICKET_STATUSES:
            raise ValueError("Cannot merge into a settled or voided ticket")
        try:
            source_items = await self.list_items(source_ticket_id, user_id)
            for line in source_items:
                line.ticket_id = target.id
            # Fold the source's fired-course map into the target's.
            merged = self._load_course_state(target)
            merged.update(self._load_course_state(source))
            target.course_state = json.dumps(merged)
            # Void the source and free its table.
            source.status = "void"
            if source.table_id is not None:
                stbl = await self.get_table(source.table_id, user_id)
                if stbl is not None and stbl.current_ticket_id == source.id:
                    stbl.state = "free"
                    stbl.current_ticket_id = None
            await self.db.commit()
            await self.db.refresh(target)
            logger.info(f"Merged ticket {source_ticket_id} into {target_ticket_id}")
            return target
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error merging ticket {source_ticket_id} into {target_ticket_id}: {str(e)}")
            raise

    async def split_ticket(
        self,
        ticket_id: int,
        strategy: str,
        user_id: str,
        n_ways: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Compute the shares a bill divides into (RST-02).

        This is a non-destructive computation (settlement to a fiscal invoice is
        a later slice): it returns the shares without mutating the ticket.

        * ``seat``   — one share per seat (lines with no seat collect under
          ``"unseated"``), each carrying its line ids and subtotal.
        * ``amount`` — ``n_ways`` equal shares of the grand total (any rounding
          remainder lands on the first share so the shares re-sum to the total).
        * ``item``   — one share per line.

        Returns ``None`` if the ticket isn't found.
        """
        ticket = await self.get_ticket(ticket_id, user_id)
        if not ticket:
            return None
        if strategy not in SPLIT_STRATEGIES:
            raise ValueError(f"Invalid split strategy. Allowed: {', '.join(SPLIT_STRATEGIES)}")
        # Divide only the unpaid remainder — lines a prior partial already billed
        # (ISSUE-070) are not part of what's left to split.
        items = await self._unsettled_items(ticket_id, user_id)
        total = round(sum(float(i.line_total or 0) for i in items), 2)

        shares: List[Dict[str, Any]] = []
        if strategy == "seat":
            buckets: Dict[str, List[OrderTicketItems]] = {}
            for i in items:
                key = str(i.seat_no) if i.seat_no is not None else "unseated"
                buckets.setdefault(key, []).append(i)
            for key, lines in buckets.items():
                shares.append({
                    "seat": key,
                    "item_ids": [line.id for line in lines],
                    "subtotal": round(sum(float(line.line_total or 0) for line in lines), 2),
                })
        elif strategy == "item":
            for i in items:
                shares.append({
                    "item_id": i.id,
                    "name": i.name,
                    "subtotal": round(float(i.line_total or 0), 2),
                })
        else:  # amount
            ways = int(n_ways or 2)
            if ways < 1:
                raise ValueError("n_ways must be at least 1")
            base = round(total / ways, 2)
            amounts = [base] * ways
            # Push the rounding remainder onto the first share.
            amounts[0] = round(total - base * (ways - 1), 2)
            shares = [{"share": idx + 1, "subtotal": amt} for idx, amt in enumerate(amounts)]

        return {"ticket_id": ticket_id, "strategy": strategy, "total": total, "shares": shares}

    # ----------------------------------------------------- service charge (F-061)
    async def set_service_charge(
        self, ticket_id: int, pct: float, user_id: str
    ) -> Optional[OrderTickets]:
        """Apply (or clear) an optional service-charge % on a ticket (F-061).

        The percentage lives on the ticket; it resolves to a separate, non-taxable
        line at check/settle time (``compute_check``). Raises ``ValueError`` for a
        negative percentage or a settled/void ticket. Returns ``None`` if the
        ticket isn't found (caller maps to 404).
        """
        ticket = await self.get_ticket(ticket_id, user_id)
        if not ticket:
            return None
        if (ticket.status or "open") in CLOSED_TICKET_STATUSES:
            raise ValueError("Cannot change the service charge on a settled or voided ticket")
        pct = float(pct or 0)
        if pct < 0:
            raise ValueError("Service charge percentage cannot be negative")
        try:
            ticket.service_charge_pct = round(pct, 4)
            await self.db.commit()
            await self.db.refresh(ticket)
            logger.info(f"Set service charge {pct}% on ticket {ticket_id}")
            return ticket
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error setting service charge on ticket {ticket_id}: {str(e)}")
            raise

    async def compute_check(
        self, ticket_id: int, user_id: str, vat_rate: float, tip_amount: float = 0.0
    ) -> Optional[Dict[str, Any]]:
        """Compute a ticket's bill — the normalized cart the settle path consumes (F-061).

        The goods (the ticket's line totals, modifiers already folded in) are the
        ONLY taxable base: VAT is charged on the goods, never on the service charge
        or the tip. The service charge is a percentage of the pre-VAT goods subtotal
        and is added as its own non-taxable line **outside the VAT base** — exactly
        like a tip (POS-13/F-012). ``amount_due`` is what the tenders must cover:
        invoice total (goods + VAT) + service charge + tip.

        Returns ``None`` if the ticket isn't found; raises ``ValueError`` on a
        negative tip.
        """
        ticket = await self.get_ticket(ticket_id, user_id)
        if not ticket:
            return None
        # Only the unpaid remainder is billable: lines a prior partial settlement
        # (ISSUE-070) already invoiced carry ``settled_at`` and drop out here, so the
        # check (and the full settle that consumes it) never re-bills a paid line.
        items = await self._unsettled_items(ticket_id, user_id)
        return self._check_for_items(ticket_id, ticket, items, vat_rate, tip_amount)

    def _check_for_items(
        self,
        ticket_id: int,
        ticket: "OrderTickets",
        items: List["OrderTicketItems"],
        vat_rate: float,
        tip_amount: float = 0.0,
    ) -> Dict[str, Any]:
        """Compute the bill for a specific set of lines — the cart the settle path
        consumes (F-061). Shared by the full check (all unpaid lines) and a partial
        settlement (ISSUE-070), which passes only the seat's / chosen lines.

        The service charge is the ticket's % applied to *these* lines' pre-VAT goods
        subtotal, so each partial pays service charge on exactly its own goods —
        outside the VAT base, like a tip. Raises ``ValueError`` on a negative tip.
        """
        tip = round(float(tip_amount or 0), 2)
        if tip < 0:
            raise ValueError("tip_amount cannot be negative")

        # Goods subtotal = the taxable base (modifier/combo pricing already folded
        # into each line_total). Voided lines never reach here — they are deleted.
        subtotal = round(sum(float(i.line_total or 0) for i in items), 2)
        vat_amount = round(subtotal * (vat_rate / 100), 2)
        total_amount = round(subtotal + vat_amount, 2)

        # Service charge: a % of the pre-VAT goods subtotal, OUTSIDE the VAT base.
        sc_pct = round(float(ticket.service_charge_pct or 0), 4)
        service_charge_amount = round(subtotal * (sc_pct / 100), 2)

        amount_due = round(total_amount + service_charge_amount + tip, 2)

        return {
            "ticket_id": ticket_id,
            "lines": [
                {
                    "item_id": i.id,
                    "name": i.name,
                    "qty": float(i.qty or 0),
                    "unit_price": float(i.unit_price or 0),
                    "line_total": float(i.line_total or 0),
                    "course": i.course,
                    "taxable": True,
                }
                for i in items
            ],
            "subtotal": subtotal,
            "vat_rate": round(float(vat_rate), 4),
            "vat_amount": vat_amount,
            "total_amount": total_amount,
            # The service charge as its own non-taxable line (outside the VAT base).
            "service_charge": {
                "pct": sc_pct,
                "amount": service_charge_amount,
                "taxable": False,
            },
            "tip_amount": tip,
            "amount_due": amount_due,
        }

    # --------------------------------------------------- check + settle (F-059)
    async def _cart_lines(
        self, items: List[OrderTicketItems], user_id: str
    ) -> List["SettleLine"]:
        """Normalize a ticket's lines into the cart-line shape the sale core needs.

        Each line's unit price is derived from its ``line_total`` (which already
        folds in modifier/combo pricing) so the rung-up receipt lines re-sum to the
        goods subtotal the invoice is stamped on.

        A **combo** line carries ``combo_id`` (and ``product_id=None``); on its own
        it would charge the bundle but deduct no stock — a silent oversell (H23,
        ISSUE-032). So it is expanded here into one cart line per component product
        (qty = component qty × line qty), which the sale core then deducts (and
        BOM-expands) exactly once. The bundle price is allocated across the
        components so the rung-up lines still re-sum to the same goods subtotal.
        """
        lines: List[SettleLine] = []
        for i in items:
            qty = float(i.qty or 0)
            line_total = float(i.line_total or 0)
            combo_id = getattr(i, "combo_id", None)
            if combo_id is not None:
                expanded = await self._expand_combo_line(combo_id, qty, line_total, user_id)
                if expanded:
                    lines.extend(expanded)
                    continue
                # Combo deleted or has no components: keep the single (non-deducting)
                # line so the charge/receipt is preserved rather than silently lost.
            unit = round(line_total / qty, 4) if qty else round(line_total, 4)
            lines.append(
                SettleLine(
                    product_id=i.product_id,
                    variant_id=i.variant_id,
                    name=i.name,
                    price=unit,
                    quantity=qty,
                    modifiers=i.modifiers,
                )
            )
        return lines

    async def _expand_combo_line(
        self, combo_id: int, line_qty: float, line_total: float, user_id: str
    ) -> Optional[List["SettleLine"]]:
        """Expand a combo line into one cart line per component product (ISSUE-032).

        Returns ``None`` when the combo can't be expanded (deleted, or no valid
        components), so the caller can keep the original line. The bundle's
        ``line_total`` is allocated across components in proportion to their catalog
        price so the expanded lines re-sum to the same goods subtotal.
        """
        combo = await self.get_combo(combo_id, user_id)
        if combo is None:
            return None
        components = self._normalize_components(self._load_components(combo))
        if not components:
            return None

        metas: List[tuple] = []
        weights: List[float] = []
        for comp in components:
            pid = comp["product_id"]
            comp_qty = float(comp.get("qty") or 1)
            product = await self._owned_product(pid, user_id)
            price = float(product.price) if product is not None else 0.0
            name = product.name if product is not None else f"product:{pid}"
            metas.append((pid, comp_qty, name))
            weights.append(price * comp_qty)

        allocations = self._allocate(line_total, weights)
        expanded: List[SettleLine] = []
        for (pid, comp_qty, name), alloc in zip(metas, allocations):
            q = round(comp_qty * line_qty, 4)
            unit = round(alloc / q, 4) if q else 0.0
            expanded.append(
                SettleLine(product_id=pid, name=name, price=unit, quantity=q)
            )
        return expanded

    @staticmethod
    def _allocate(total: float, weights: List[float]) -> List[float]:
        """Split ``total`` across ``weights`` to cents; the last absorbs the remainder.

        Falls back to an equal split when the weights are all zero (free components),
        so the allocation always sums back to ``total`` exactly.
        """
        total = round(float(total), 2)
        n = len(weights)
        if n == 0:
            return []
        wsum = sum(weights)
        if wsum > 0:
            allocs = [round(total * w / wsum, 2) for w in weights]
        else:
            allocs = [round(total / n, 2) for _ in weights]
        allocs[-1] = round(total - sum(allocs[:-1]), 2)
        return allocs

    async def build_proforma(
        self,
        ticket_id: int,
        user_id: str,
        client: Any,
        vat_rate: float,
        tip_amount: float = 0.0,
    ) -> Optional[Dict[str, Any]]:
        """Render an 80mm always-Arabic **proforma** check for a ticket (F-059).

        The proforma (*فاتورة مبدئية*) is the bill the customer reviews BEFORE
        paying: it carries the full check breakdown (goods, VAT, service charge,
        tip, amount due) but **no QR and no stamp**, so it can never be mistaken
        for a tax invoice. The body renders in Arabic regardless of UI language
        (the fiscal-document invariant). Returns ``None`` if the ticket isn't found.
        """
        check = await self.compute_check(ticket_id, user_id, vat_rate, tip_amount)
        if check is None:
            return None

        # Reflect on the floor that a bill is out (U4.1): flip the dine-in table
        # occupied -> bill_printed and persist it, so the state is real across
        # sessions/devices rather than a browser-only tile flip. Non-fiscal — the
        # ticket stays open and nothing is minted. Takeaway/delivery have no table.
        ticket = await self.get_ticket(ticket_id, user_id)
        if ticket is not None and ticket.table_id is not None:
            table = await self.get_table(ticket.table_id, user_id)
            if (
                table is not None
                and table.current_ticket_id == ticket.id
                and (table.state or "free") == "occupied"
            ):
                table.state = "bill_printed"
                await self.db.commit()

        from datetime import datetime

        from services.escpos import build_receipt_base64

        items = await self.list_items(ticket_id, user_id)
        line_items = [
            {
                "name": i.name,
                "name_ar": None,
                "quantity": float(i.qty or 0),
                "price": (
                    round(float(i.line_total or 0) / float(i.qty), 4)
                    if i.qty
                    else float(i.line_total or 0)
                ),
                "discount": 0,
            }
            for i in items
        ]
        sc_amount = check["service_charge"]["amount"]
        # H26 (#45): render through the merchant's default receipt template (its QR
        # knob is moot here — a proforma never carries a QR — but header/footer/
        # logo/font_size still apply).
        from services.receipt_templates import load_default_template

        template = await load_default_template(self.db, user_id)

        # H26/U5.2 (#47): route the proforma to the merchant's saved/selected
        # receipt printer — its paper_size overrides the template's so the raster
        # matches the actual head, and the resolved device is echoed back so the
        # browser streams to it rather than re-prompting for any USB device.
        from services.printers import printer_echo, resolve_printer

        printer = await resolve_printer(self.db, user_id, "receipt")
        if printer is not None and printer.paper_size:
            template = {**(template or {}), "paper_size": printer.paper_size}

        proforma_base64 = build_receipt_base64(
            seller_name=client.business_name or "Business",
            vat_number=client.vat_number or "",
            invoice_number=f"PRO-{ticket_id}",
            issue_date=datetime.now().strftime("%Y-%m-%d %H:%M"),
            line_items=line_items,
            subtotal=check["subtotal"],
            discount=0,
            vat_amount=check["vat_amount"],
            total_amount=check["total_amount"],
            tip_amount=check["tip_amount"],
            service_charge=sc_amount,
            proforma=True,
            template=template,
        )
        return {
            **check,
            "document_type": "proforma",
            "title_ar": "فاتورة مبدئية",
            "is_fiscal": False,
            "has_qr": False,
            "has_stamp": False,
            "proforma_base64": proforma_base64,
            "printer": printer_echo(printer),
        }

    async def settle_ticket(
        self,
        ticket_id: int,
        user_id: str,
        client: Any,
        vat_rate: float,
        *,
        tender_specs: List[Dict[str, Any]],
        tip_amount: float = 0.0,
        payment_method: str = "cash",
        payment_breakdown_json: Optional[str] = None,
        customer_name: Optional[str] = None,
        customer_vat_number: Optional[str] = None,
        allow_negative_stock: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Settle a ticket into a real ZATCA invoice via the shared sale core (F-059).

        Builds the normalized cart from the ticket (lines + modifiers + combos +
        service charge + BOM components) and mints a fiscal sale through the exact
        same ``services.sale_core.execute_sale`` path the POS uses — tender capture,
        inventory deduction (incl. BOM expansion), shift accumulation, ECDSA stamp.

        **Atomic:** the ticket close (``settled``) and the table free are staged in
        the same session, so ``execute_sale``'s single commit either persists the
        invoice **and** the close together, or — on a declined card — raises before
        commit, rolling back everything: the ticket stays ``open``, the table stays
        occupied, and no invoice is minted.

        Returns ``{"result": SaleResult, "check": dict}``, ``None`` if the ticket
        isn't found, or raises ``ValueError`` for a closed/empty ticket.
        """
        ticket = await self.get_ticket(ticket_id, user_id)
        if not ticket:
            return None
        if (ticket.status or "open") in CLOSED_TICKET_STATUSES:
            raise ValueError("Ticket is already settled or voided")
        # The full settle clears the unpaid remainder — lines a prior partial
        # settlement (ISSUE-070) already billed are excluded so they aren't charged
        # twice; the close still frees the table.
        items = await self._unsettled_items(ticket_id, user_id)
        if not items:
            raise ValueError("Cannot settle an empty ticket")

        check = await self.compute_check(ticket_id, user_id, vat_rate, tip_amount)
        lines = await self._cart_lines(items, user_id)

        # Stage the ticket close + table free in THIS session so they commit
        # atomically with the fiscal sale below. execute_sale commits once; a
        # declined card raises before that commit, leaving the ticket open and the
        # table occupied (nothing here is persisted).
        from datetime import datetime

        now = datetime.now()
        for i in items:
            i.settled_at = now
        ticket.status = "settled"
        if ticket.table_id is not None:
            table = await self.get_table(ticket.table_id, user_id)
            if table is not None and table.current_ticket_id == ticket.id:
                table.state = "free"
                table.current_ticket_id = None

        from services.sale_core import NormalizedCart, execute_sale

        result = await execute_sale(
            self.db,
            NormalizedCart(
                user_id=user_id,
                client=client,
                lines=lines,
                subtotal=check["subtotal"],
                discount_amount=0.0,
                vat_rate=check["vat_rate"],
                vat_amount=check["vat_amount"],
                total_amount=check["total_amount"],
                tender_specs=tender_specs,
                payment_method=payment_method,
                payment_breakdown_json=payment_breakdown_json,
                tip_amount=check["tip_amount"],
                service_charge=check["service_charge"]["amount"],
                customer_name=customer_name or ticket.customer_name,
                buyer_vat=customer_vat_number,
                branch_id=ticket.branch_id,
                allow_negative_stock=allow_negative_stock,
                # F-062: deplete BOM-backed recipe components inside the same atomic
                # stock transaction as the finished sale.
                expand_bom=True,
            ),
        )
        logger.info(f"Settled ticket {ticket_id} -> invoice {result.transaction.invoice_number}")
        return {"result": result, "check": check, "ticket": ticket}

    def _resolve_partial_items(
        self,
        unsettled: List["OrderTicketItems"],
        item_ids: Optional[List[int]],
        seat_no: Optional[int],
    ) -> List["OrderTicketItems"]:
        """Pick the subset of the unpaid remainder a partial settlement bills (ISSUE-070).

        **By seat:** every unpaid line carrying ``seat_no``. **By item:** the unpaid
        lines whose ids are listed. Exactly one selector must be given. Raises
        ``ValueError`` if neither/both are given, if the selection is empty (nothing
        unpaid matches), or if an ``item_ids`` entry isn't an unpaid line on this
        ticket (already paid, voided, or another ticket's) — so a caller can't bill
        a line twice or reach across tickets.
        """
        has_items = bool(item_ids)
        has_seat = seat_no is not None
        if has_items == has_seat:
            raise ValueError("Provide exactly one of item_ids or seat_no")

        if has_seat:
            target = [i for i in unsettled if i.seat_no == seat_no]
            if not target:
                raise ValueError(f"No unsettled items for seat {seat_no}")
            return target

        by_id = {i.id: i for i in unsettled}
        target = []
        for iid in item_ids:
            item = by_id.get(iid)
            if item is None:
                raise ValueError(f"Item {iid} is not an unsettled line on this ticket")
            target.append(item)
        return target

    async def compute_partial_check(
        self,
        ticket_id: int,
        user_id: str,
        vat_rate: float,
        *,
        item_ids: Optional[List[int]] = None,
        seat_no: Optional[int] = None,
        tip_amount: float = 0.0,
    ) -> Optional[Dict[str, Any]]:
        """The bill for the subset a partial settlement will charge (ISSUE-070).

        Lets the router validate split tenders against the partial's ``amount_due``
        before any fiscal side effect runs. Returns ``None`` if the ticket isn't
        found; raises ``ValueError`` on a closed ticket or an invalid selection.
        """
        ticket = await self.get_ticket(ticket_id, user_id)
        if not ticket:
            return None
        if (ticket.status or "open") in CLOSED_TICKET_STATUSES:
            raise ValueError("Ticket is already settled or voided")
        unsettled = await self._unsettled_items(ticket_id, user_id)
        target = self._resolve_partial_items(unsettled, item_ids, seat_no)
        return self._check_for_items(ticket_id, ticket, target, vat_rate, tip_amount)

    async def settle_partial(
        self,
        ticket_id: int,
        user_id: str,
        client: Any,
        vat_rate: float,
        *,
        item_ids: Optional[List[int]] = None,
        seat_no: Optional[int] = None,
        tender_specs: List[Dict[str, Any]],
        tip_amount: float = 0.0,
        payment_method: str = "cash",
        payment_breakdown_json: Optional[str] = None,
        customer_name: Optional[str] = None,
        customer_vat_number: Optional[str] = None,
        allow_negative_stock: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Settle part of a ticket into its own ZATCA invoice (ISSUE-070).

        Bills the chosen subset (a seat's lines, or specific items) through the very
        same atomic ``execute_sale`` path a full settle uses — tender capture, stock
        deduction (incl. BOM/combo expansion), ECDSA stamp. The billed lines are
        stamped ``settled_at`` so they drop off the unpaid remainder; the ticket
        stays ``open`` and the table stays occupied while anything is still unpaid.
        Clearing the **last** unpaid line closes the ticket and frees the table —
        the remainder's final partial settles exactly like the full path.

        **Atomic:** the line stamps + any close are staged in this session, so a
        declined card raises before ``execute_sale``'s single commit and nothing
        persists. Returns ``{"result", "check", "ticket", "fully_settled"}``, or
        ``None`` if the ticket isn't found; raises ``ValueError`` for a closed ticket
        or an invalid selection.
        """
        ticket = await self.get_ticket(ticket_id, user_id)
        if not ticket:
            return None
        if (ticket.status or "open") in CLOSED_TICKET_STATUSES:
            raise ValueError("Ticket is already settled or voided")

        unsettled = await self._unsettled_items(ticket_id, user_id)
        target = self._resolve_partial_items(unsettled, item_ids, seat_no)
        check = self._check_for_items(ticket_id, ticket, target, vat_rate, tip_amount)
        lines = await self._cart_lines(target, user_id)

        # Stage the line stamps + (when this clears the remainder) the close in THIS
        # session so they commit atomically with the fiscal sale. A declined card
        # raises before execute_sale's commit — nothing here persists.
        from datetime import datetime

        now = datetime.now()
        target_ids = {i.id for i in target}
        for i in target:
            i.settled_at = now
        fully_settled = all(i.id in target_ids for i in unsettled)
        if fully_settled:
            ticket.status = "settled"
            if ticket.table_id is not None:
                table = await self.get_table(ticket.table_id, user_id)
                if table is not None and table.current_ticket_id == ticket.id:
                    table.state = "free"
                    table.current_ticket_id = None

        from services.sale_core import NormalizedCart, execute_sale

        result = await execute_sale(
            self.db,
            NormalizedCart(
                user_id=user_id,
                client=client,
                lines=lines,
                subtotal=check["subtotal"],
                discount_amount=0.0,
                vat_rate=check["vat_rate"],
                vat_amount=check["vat_amount"],
                total_amount=check["total_amount"],
                tender_specs=tender_specs,
                payment_method=payment_method,
                payment_breakdown_json=payment_breakdown_json,
                tip_amount=check["tip_amount"],
                service_charge=check["service_charge"]["amount"],
                customer_name=customer_name or ticket.customer_name,
                buyer_vat=customer_vat_number,
                branch_id=ticket.branch_id,
                allow_negative_stock=allow_negative_stock,
                expand_bom=True,
            ),
        )
        logger.info(
            f"Partially settled ticket {ticket_id} "
            f"(fully={fully_settled}) -> invoice {result.transaction.invoice_number}"
        )
        return {
            "result": result,
            "check": check,
            "ticket": ticket,
            "fully_settled": fully_settled,
        }

    async def all_day_fired_count(self, user_id: str) -> Dict[str, Any]:
        """All-day count of fired items the caller owns (RST-02).

        A shared kitchen/server view of outstanding fired work: total fired
        quantity plus a per-product breakdown across all of the caller's open
        tickets. Settled/void tickets are excluded.
        """
        rows = (
            await self.db.execute(
                select(OrderTicketItems, OrderTickets.status)
                .join(OrderTickets, OrderTickets.id == OrderTicketItems.ticket_id)
                .where(
                    OrderTicketItems.user_id == user_id,
                    OrderTicketItems.fire_state == "fired",
                    OrderTickets.status.notin_(CLOSED_TICKET_STATUSES),
                )
            )
        ).all()
        by_product: Dict[str, Dict[str, Any]] = {}
        total_qty = 0.0
        for item, _status in rows:
            total_qty += float(item.qty or 0)
            label = item.name or (f"product:{item.product_id}" if item.product_id else "item")
            entry = by_product.setdefault(label, {"name": label, "qty": 0.0})
            entry["qty"] += float(item.qty or 0)
        return {
            "fired_item_count": len(rows),
            "fired_qty": round(total_qty, 2),
            "by_product": list(by_product.values()),
        }

    # ----------------------------------------------------- prep stations (F-057)
    async def list_prep_stations(self, user_id: str) -> List[PrepStations]:
        result = await self.db.execute(
            select(PrepStations)
            .where(PrepStations.user_id == user_id)
            .order_by(PrepStations.sort_order.asc(), PrepStations.id.asc())
        )
        return result.scalars().all()

    async def get_prep_station(self, station_id: int, user_id: str) -> Optional[PrepStations]:
        result = await self.db.execute(
            select(PrepStations).where(
                PrepStations.id == station_id, PrepStations.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def create_prep_station(
        self, data: Dict[str, Any], user_id: str, client_id: Optional[int]
    ) -> PrepStations:
        try:
            station = PrepStations(
                user_id=user_id,
                client_id=client_id,
                name=data["name"],
                name_ar=data.get("name_ar"),
                sort_order=int(data.get("sort_order") or 0),
            )
            self.db.add(station)
            await self.db.commit()
            await self.db.refresh(station)
            logger.info(f"Created prep station {station.id} for user {user_id}")
            return station
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating prep station: {str(e)}")
            raise

    async def update_prep_station(
        self, station_id: int, updates: Dict[str, Any], user_id: str
    ) -> Optional[PrepStations]:
        station = await self.get_prep_station(station_id, user_id)
        if not station:
            return None
        try:
            editable = ("name", "name_ar", "sort_order")
            for key, value in updates.items():
                if key in editable and hasattr(station, key):
                    setattr(station, key, value)
            await self.db.commit()
            await self.db.refresh(station)
            return station
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating prep station {station_id}: {str(e)}")
            raise

    async def delete_prep_station(self, station_id: int, user_id: str) -> bool:
        station = await self.get_prep_station(station_id, user_id)
        if not station:
            return False
        try:
            await self.db.delete(station)
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting prep station {station_id}: {str(e)}")
            raise

    # ------------------------------------------------------ kitchen display (F-057)
    @staticmethod
    def _kds_line_snapshot(line: OrderTicketItems) -> Dict[str, Any]:
        """Render a fired line into the KOT/board snapshot — no price ever (F-057)."""
        names: List[str] = []
        try:
            mods = json.loads(line.modifiers) if line.modifiers else []
            if isinstance(mods, list):
                names = [str(m.get("name")) for m in mods if isinstance(m, dict) and m.get("name")]
        except (ValueError, TypeError):
            names = []
        return {
            "item_id": line.id,
            "name": line.name,
            "qty": float(line.qty or 0),
            "course": line.course,
            "notes": line.notes,
            "modifiers": names,
        }

    def _materialize_kds_for_fire(
        self, ticket: OrderTickets, course: str, fired_lines: List[OrderTicketItems], user_id: str
    ) -> List[KdsTickets]:
        """Group the fired lines by prep-station and stage one card per station.

        Caller stages these in the open fire transaction so they commit atomically
        with the line ``fire_state`` flip. Lines with no ``prep_station_id`` collect
        on a single unrouted (expo) card. Returns the staged (un-flushed) cards.
        """
        by_station: Dict[Optional[int], List[OrderTicketItems]] = {}
        for line in fired_lines:
            by_station.setdefault(line.prep_station_id, []).append(line)
        cards: List[KdsTickets] = []
        for station_id, lines in by_station.items():
            card = KdsTickets(
                user_id=user_id,
                client_id=ticket.client_id,
                order_ticket_id=ticket.id,
                table_id=ticket.table_id,
                station_id=station_id,
                course=course,
                status="active",
                item_ids=json.dumps([line.id for line in lines]),
                items_json=json.dumps([self._kds_line_snapshot(line) for line in lines]),
                customer_name=ticket.customer_name,
                order_type=ticket.order_type,
            )
            self.db.add(card)
            cards.append(card)
        return cards

    @staticmethod
    def _kds_to_dict(card: KdsTickets) -> Dict[str, Any]:
        try:
            items = json.loads(card.items_json) if card.items_json else []
        except (ValueError, TypeError):
            items = []
        return {
            "id": card.id,
            "order_ticket_id": card.order_ticket_id,
            "table_id": card.table_id,
            "station_id": card.station_id,
            "course": card.course,
            "status": card.status,
            "customer_name": card.customer_name,
            "order_type": card.order_type,
            "items": items,
            "fired_at": card.fired_at.isoformat() if card.fired_at else None,
            "bumped_at": card.bumped_at.isoformat() if card.bumped_at else None,
        }

    async def list_kds_tickets(
        self, user_id: str, status: Optional[str] = "active", station_id: Optional[int] = None
    ) -> List[KdsTickets]:
        """The kitchen board: cards the caller owns, newest fired first (F-057)."""
        query = select(KdsTickets).where(KdsTickets.user_id == user_id)
        if status is not None:
            query = query.where(KdsTickets.status == status)
        if station_id is not None:
            query = query.where(KdsTickets.station_id == station_id)
        query = query.order_by(KdsTickets.fired_at.asc(), KdsTickets.id.asc())
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_kds_ticket(self, kds_id: int, user_id: str) -> Optional[KdsTickets]:
        result = await self.db.execute(
            select(KdsTickets).where(
                KdsTickets.id == kds_id, KdsTickets.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _kds_item_ids(card: KdsTickets) -> List[int]:
        try:
            ids = json.loads(card.item_ids) if card.item_ids else []
        except (ValueError, TypeError):
            return []
        return [int(i) for i in ids] if isinstance(ids, list) else []

    async def _set_lines_fire_state(self, item_ids: List[int], user_id: str, state: str) -> None:
        """Keep the source order lines' ``fire_state`` in sync with their card."""
        for item_id in item_ids:
            line = await self.get_item(item_id, user_id)
            if line is not None:
                line.fire_state = state

    async def bump_kds_ticket(self, kds_id: int, user_id: str) -> Optional[Dict[str, Any]]:
        """Mark a card done — clear it from the active board (F-057).

        The card goes ``active -> bumped`` (stamped ``bumped_at``) and its source
        order lines advance to ``bumped`` so the server's screen and the kitchen
        agree. Idempotent on an already-bumped card. Returns ``None`` if not found.
        """
        card = await self.get_kds_ticket(kds_id, user_id)
        if not card:
            return None
        try:
            card.status = "bumped"
            card.bumped_at = datetime.now()
            await self._set_lines_fire_state(self._kds_item_ids(card), user_id, "bumped")
            await self.db.commit()
            await self.db.refresh(card)
            payload = self._kds_to_dict(card)
            kds_broker.publish(user_id, {"type": "bumped", "card": payload})
            logger.info(f"Bumped KDS card {kds_id}")
            return payload
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error bumping KDS card {kds_id}: {str(e)}")
            raise

    async def recall_kds_ticket(self, kds_id: int, user_id: str) -> Optional[Dict[str, Any]]:
        """Restore a mistakenly-bumped card to the active board (F-057).

        The card goes ``bumped -> active`` (``bumped_at`` cleared) and its source
        lines drop back to ``fired``. Returns ``None`` if the card isn't found.
        """
        card = await self.get_kds_ticket(kds_id, user_id)
        if not card:
            return None
        try:
            card.status = "active"
            card.bumped_at = None
            await self._set_lines_fire_state(self._kds_item_ids(card), user_id, "fired")
            await self.db.commit()
            await self.db.refresh(card)
            payload = self._kds_to_dict(card)
            kds_broker.publish(user_id, {"type": "recalled", "card": payload})
            logger.info(f"Recalled KDS card {kds_id}")
            return payload
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error recalling KDS card {kds_id}: {str(e)}")
            raise

    async def kot_payload(self, kds_id: int, user_id: str) -> Optional[Dict[str, Any]]:
        """Build the per-station KOT model for a card — modifiers grouped by course,
        **no prices** (F-057). Returns ``None`` if the card isn't found.
        """
        card = await self.get_kds_ticket(kds_id, user_id)
        if not card:
            return None
        station = (
            await self.get_prep_station(card.station_id, user_id)
            if card.station_id is not None
            else None
        )
        try:
            items = json.loads(card.items_json) if card.items_json else []
        except (ValueError, TypeError):
            items = []
        # Group the snapshot items by course (this card is usually one course, but
        # group defensively so the KOT layout is identical to the multi-course one).
        courses: Dict[str, List[Dict[str, Any]]] = {}
        for it in items:
            courses.setdefault(it.get("course") or "mains", []).append(
                {
                    "name": it.get("name"),
                    "qty": it.get("qty"),
                    "notes": it.get("notes"),
                    "modifiers": it.get("modifiers") or [],
                }
            )
        return {
            "kds_ticket_id": card.id,
            "order_ticket_id": card.order_ticket_id,
            "station_id": card.station_id,
            "station_name": station.name if station is not None else None,
            "station_name_ar": station.name_ar if station is not None else None,
            "table_id": card.table_id,
            "fired_at": card.fired_at.isoformat() if card.fired_at else None,
            # One entry per course; items carry NO price field (kitchen ticket).
            "courses": [{"course": c, "items": lines} for c, lines in courses.items()],
        }

    # ------------------------------------------------------- modifier groups
    async def list_modifier_groups(self, user_id: str) -> List[ModifierGroups]:
        result = await self.db.execute(
            select(ModifierGroups)
            .where(ModifierGroups.user_id == user_id)
            .order_by(ModifierGroups.id.asc())
        )
        return result.scalars().all()

    async def get_modifier_group(self, group_id: int, user_id: str) -> Optional[ModifierGroups]:
        result = await self.db.execute(
            select(ModifierGroups).where(
                ModifierGroups.id == group_id, ModifierGroups.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def create_modifier_group(
        self, data: Dict[str, Any], user_id: str, client_id: Optional[int]
    ) -> ModifierGroups:
        try:
            group = ModifierGroups(
                user_id=user_id,
                client_id=client_id,
                name=data["name"],
                name_ar=data.get("name_ar"),
                required=bool(data.get("required", False)),
                min_select=int(data.get("min_select") or 0),
                max_select=int(data["max_select"]) if data.get("max_select") is not None else 1,
            )
            self.db.add(group)
            await self.db.commit()
            await self.db.refresh(group)
            logger.info(f"Created modifier group {group.id} for user {user_id}")
            return group
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating modifier group: {str(e)}")
            raise

    async def update_modifier_group(
        self, group_id: int, updates: Dict[str, Any], user_id: str
    ) -> Optional[ModifierGroups]:
        group = await self.get_modifier_group(group_id, user_id)
        if not group:
            return None
        try:
            editable = ("name", "name_ar", "required", "min_select", "max_select")
            for key, value in updates.items():
                if key in editable and hasattr(group, key):
                    setattr(group, key, value)
            await self.db.commit()
            await self.db.refresh(group)
            return group
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating modifier group {group_id}: {str(e)}")
            raise

    async def delete_modifier_group(self, group_id: int, user_id: str) -> bool:
        group = await self.get_modifier_group(group_id, user_id)
        if not group:
            return False
        try:
            # Cascade: drop the group's modifiers and any product attachments so we
            # never leave orphaned children pointing at a vanished group.
            for mod in await self.list_modifiers(group_id, user_id):
                await self.db.delete(mod)
            links = (
                await self.db.execute(
                    select(ProductModifierGroups).where(
                        ProductModifierGroups.group_id == group_id,
                        ProductModifierGroups.user_id == user_id,
                    )
                )
            ).scalars().all()
            for link in links:
                await self.db.delete(link)
            await self.db.delete(group)
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting modifier group {group_id}: {str(e)}")
            raise

    # ------------------------------------------------------------- modifiers
    async def list_modifiers(self, group_id: int, user_id: str) -> List[Modifiers]:
        result = await self.db.execute(
            select(Modifiers)
            .where(Modifiers.group_id == group_id, Modifiers.user_id == user_id)
            .order_by(Modifiers.id.asc())
        )
        return result.scalars().all()

    async def get_modifier(self, modifier_id: int, user_id: str) -> Optional[Modifiers]:
        result = await self.db.execute(
            select(Modifiers).where(
                Modifiers.id == modifier_id, Modifiers.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def create_modifier(
        self, group_id: int, data: Dict[str, Any], user_id: str, client_id: Optional[int]
    ) -> Optional[Modifiers]:
        group = await self.get_modifier_group(group_id, user_id)
        if not group:
            return None  # caller maps to 404
        try:
            modifier = Modifiers(
                user_id=user_id,
                client_id=client_id,
                group_id=group_id,
                name=data["name"],
                name_ar=data.get("name_ar"),
                price_delta=round(float(data.get("price_delta") or 0), 2),
            )
            self.db.add(modifier)
            await self.db.commit()
            await self.db.refresh(modifier)
            logger.info(f"Created modifier {modifier.id} in group {group_id}")
            return modifier
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating modifier in group {group_id}: {str(e)}")
            raise

    async def update_modifier(
        self, modifier_id: int, updates: Dict[str, Any], user_id: str
    ) -> Optional[Modifiers]:
        modifier = await self.get_modifier(modifier_id, user_id)
        if not modifier:
            return None
        try:
            editable = ("name", "name_ar", "price_delta")
            for key, value in updates.items():
                if key in editable and hasattr(modifier, key):
                    setattr(modifier, key, value)
            modifier.price_delta = round(float(modifier.price_delta or 0), 2)
            await self.db.commit()
            await self.db.refresh(modifier)
            return modifier
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating modifier {modifier_id}: {str(e)}")
            raise

    async def delete_modifier(self, modifier_id: int, user_id: str) -> bool:
        modifier = await self.get_modifier(modifier_id, user_id)
        if not modifier:
            return False
        try:
            await self.db.delete(modifier)
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting modifier {modifier_id}: {str(e)}")
            raise

    # ----------------------------------------------- product ↔ group attachments
    async def list_product_groups(self, product_id: int, user_id: str) -> List[Dict[str, Any]]:
        """Modifier groups attached to a product, each with its modifiers (F-056)."""
        links = (
            await self.db.execute(
                select(ProductModifierGroups).where(
                    ProductModifierGroups.product_id == product_id,
                    ProductModifierGroups.user_id == user_id,
                )
            )
        ).scalars().all()
        out: List[Dict[str, Any]] = []
        for link in links:
            group = await self.get_modifier_group(link.group_id, user_id)
            if group is None:
                continue
            mods = await self.list_modifiers(group.id, user_id)
            out.append({
                "id": group.id,
                "name": group.name,
                "name_ar": group.name_ar,
                "required": bool(group.required),
                "min_select": group.min_select,
                "max_select": group.max_select,
                "modifiers": [
                    {
                        "id": m.id,
                        "name": m.name,
                        "name_ar": m.name_ar,
                        "price_delta": float(m.price_delta or 0),
                    }
                    for m in mods
                ],
            })
        return out

    async def attach_group_to_product(
        self, product_id: int, group_id: int, user_id: str, client_id: Optional[int]
    ) -> Optional[ProductModifierGroups]:
        """Attach a modifier group to a product (idempotent). ``None`` if either is
        not owned by the caller (caller maps to 404)."""
        product = await self._owned_product(product_id, user_id)
        group = await self.get_modifier_group(group_id, user_id)
        if product is None or group is None:
            return None
        existing = (
            await self.db.execute(
                select(ProductModifierGroups).where(
                    ProductModifierGroups.product_id == product_id,
                    ProductModifierGroups.group_id == group_id,
                    ProductModifierGroups.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        try:
            link = ProductModifierGroups(
                user_id=user_id,
                client_id=client_id,
                product_id=product_id,
                group_id=group_id,
            )
            self.db.add(link)
            await self.db.commit()
            await self.db.refresh(link)
            return link
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error attaching group {group_id} to product {product_id}: {str(e)}")
            raise

    async def detach_group_from_product(
        self, product_id: int, group_id: int, user_id: str
    ) -> bool:
        link = (
            await self.db.execute(
                select(ProductModifierGroups).where(
                    ProductModifierGroups.product_id == product_id,
                    ProductModifierGroups.group_id == group_id,
                    ProductModifierGroups.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if link is None:
            return False
        try:
            await self.db.delete(link)
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error detaching group {group_id} from product {product_id}: {str(e)}")
            raise

    # ---------------------------------------------------------------- combos
    async def list_combos(self, user_id: str) -> List[Combos]:
        result = await self.db.execute(
            select(Combos).where(Combos.user_id == user_id).order_by(Combos.id.asc())
        )
        return result.scalars().all()

    async def get_combo(self, combo_id: int, user_id: str) -> Optional[Combos]:
        result = await self.db.execute(
            select(Combos).where(Combos.id == combo_id, Combos.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def create_combo(
        self, data: Dict[str, Any], user_id: str, client_id: Optional[int]
    ) -> Combos:
        components = self._normalize_components(data.get("components"))
        try:
            combo = Combos(
                user_id=user_id,
                client_id=client_id,
                name=data["name"],
                name_ar=data.get("name_ar"),
                bundle_price=round(float(data.get("bundle_price") or 0), 2),
                components=json.dumps(components),
                is_active=bool(data.get("is_active", True)),
            )
            self.db.add(combo)
            await self.db.commit()
            await self.db.refresh(combo)
            logger.info(f"Created combo {combo.id} for user {user_id}")
            return combo
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating combo: {str(e)}")
            raise

    async def update_combo(
        self, combo_id: int, updates: Dict[str, Any], user_id: str
    ) -> Optional[Combos]:
        combo = await self.get_combo(combo_id, user_id)
        if not combo:
            return None
        try:
            if "components" in updates:
                combo.components = json.dumps(self._normalize_components(updates["components"]))
            for key in ("name", "name_ar", "is_active"):
                if key in updates and updates[key] is not None:
                    setattr(combo, key, updates[key])
            if updates.get("bundle_price") is not None:
                combo.bundle_price = round(float(updates["bundle_price"]), 2)
            await self.db.commit()
            await self.db.refresh(combo)
            return combo
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating combo {combo_id}: {str(e)}")
            raise

    async def delete_combo(self, combo_id: int, user_id: str) -> bool:
        combo = await self.get_combo(combo_id, user_id)
        if not combo:
            return False
        try:
            await self.db.delete(combo)
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting combo {combo_id}: {str(e)}")
            raise

    async def combo_component_sum(self, combo: Combos, user_id: str) -> float:
        """Sum of the combo components' catalog prices × their qty (F-056).

        The bundle price overrides this; surfacing it lets the menu-builder show
        the saving and lets a test assert ``bundle_price < component_sum``.
        """
        total = 0.0
        for comp in self._load_components(combo):
            pid = comp.get("product_id")
            cqty = float(comp.get("qty") or 1)
            if pid is None:
                continue
            product = await self._owned_product(pid, user_id)
            if product is not None:
                total += float(product.price) * cqty
        return round(total, 2)

    # --------------------------------------------------- bill of materials (F-062)
    async def list_bom(self, parent_product_id: int, user_id: str) -> List[BillOfMaterials]:
        """The BOM rows (components) of a parent product, owner-scoped (F-062)."""
        result = await self.db.execute(
            select(BillOfMaterials)
            .where(
                BillOfMaterials.parent_product_id == parent_product_id,
                BillOfMaterials.user_id == user_id,
            )
            .order_by(BillOfMaterials.id.asc())
        )
        return result.scalars().all()

    async def get_bom_entry(self, bom_id: int, user_id: str) -> Optional[BillOfMaterials]:
        result = await self.db.execute(
            select(BillOfMaterials).where(
                BillOfMaterials.id == bom_id, BillOfMaterials.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def create_bom_entry(
        self, parent_product_id: int, data: Dict[str, Any], user_id: str, client_id: Optional[int]
    ) -> Optional[BillOfMaterials]:
        """Add a component to a parent product's BOM (F-062).

        Returns ``None`` if the parent or component isn't an owned product (caller
        maps to 404). Raises ``ValueError`` on a self-referencing component or a
        non-positive ``qty_per``.
        """
        parent = await self._owned_product(parent_product_id, user_id)
        component_id = data.get("component_product_id")
        component = (
            await self._owned_product(component_id, user_id) if component_id is not None else None
        )
        if parent is None or component is None:
            return None
        if int(component_id) == int(parent_product_id):
            raise ValueError("A product cannot be a component of itself")
        qty_per = float(data.get("qty_per") or 0)
        if qty_per <= 0:
            raise ValueError("qty_per must be greater than zero")
        try:
            entry = BillOfMaterials(
                user_id=user_id,
                client_id=client_id,
                parent_product_id=parent_product_id,
                component_product_id=int(component_id),
                qty_per=round(qty_per, 4),
            )
            self.db.add(entry)
            await self.db.commit()
            await self.db.refresh(entry)
            logger.info(
                f"Added BOM component {component_id} (x{qty_per}) to product {parent_product_id}"
            )
            return entry
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating BOM entry for product {parent_product_id}: {str(e)}")
            raise

    async def update_bom_entry(
        self, bom_id: int, updates: Dict[str, Any], user_id: str
    ) -> Optional[BillOfMaterials]:
        entry = await self.get_bom_entry(bom_id, user_id)
        if not entry:
            return None
        if "qty_per" in updates and updates["qty_per"] is not None:
            qty_per = float(updates["qty_per"])
            if qty_per <= 0:
                raise ValueError("qty_per must be greater than zero")
            entry.qty_per = round(qty_per, 4)
        try:
            await self.db.commit()
            await self.db.refresh(entry)
            return entry
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating BOM entry {bom_id}: {str(e)}")
            raise

    async def delete_bom_entry(self, bom_id: int, user_id: str) -> bool:
        entry = await self.get_bom_entry(bom_id, user_id)
        if not entry:
            return False
        try:
            await self.db.delete(entry)
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting BOM entry {bom_id}: {str(e)}")
            raise

    async def parent_cogs(self, parent_product_id: int, user_id: str) -> float:
        """Roll the component costs up to a cost-of-goods value on the parent (F-062).

        Sum of each component's ``cost_price × qty_per``. This is the hook a margin
        report (F-068) later consumes — no report is produced here.
        """
        total = 0.0
        for entry in await self.list_bom(parent_product_id, user_id):
            component = await self._owned_product(entry.component_product_id, user_id)
            if component is not None:
                total += float(component.cost_price or 0) * float(entry.qty_per or 0)
        return round(total, 4)

    # BOM depletion is owned by the atomic settle path (F-059): settle_ticket builds
    # the normalized cart and execute_sale(expand_bom=True) deducts each recipe
    # component exactly once, inside the same transaction as the fiscal sale. There
    # is deliberately NO standalone ticket-level depletion method — a second
    # depletion path would deduct the very same components settle already deducts,
    # double-counting every recipe component per sale (ISSUE-104, U4.1).

    # ----------------------------------------------------------------- helpers
    async def _resolve_modifiers(
        self, raw: Any, product_id: Optional[int], user_id: str
    ) -> tuple:
        """Validate + price a modifier selection (F-056).

        ``raw`` is a list of modifier ids (or dicts carrying ``id``/``modifier_id``).
        Required groups attached to the product are enforced; the price deltas are
        summed (once per line, before VAT) and the selection is serialized as
        ``[{id, group_id, name, name_ar, price_delta}]`` for the kitchen ticket.

        Returns ``(modifier_total, serialized_json_or_None)`` and raises
        ``ValueError`` when a required group is unsatisfied or a group's
        ``max_select`` is exceeded.
        """
        selected_ids = self._extract_modifier_ids(raw)

        # Resolve each selected id to an owned Modifier row.
        chosen: List[Modifiers] = []
        for mid in selected_ids:
            mod = await self.get_modifier(mid, user_id)
            if mod is None:
                raise ValueError(f"Modifier {mid} not found")
            chosen.append(mod)

        # Enforce the product's attached groups (required + min/max).
        if product_id is not None:
            groups = await self.list_product_groups(product_id, user_id)
            for g in groups:
                count = sum(1 for m in chosen if m.group_id == g["id"])
                min_sel = g["min_select"] or 0
                if g["required"] and min_sel < 1:
                    min_sel = 1  # a required group needs at least one pick
                if g["required"] and count < min_sel:
                    raise ValueError(
                        f"Required modifier group '{g['name']}' needs at least "
                        f"{min_sel} selection(s)"
                    )
                max_sel = g["max_select"]
                if max_sel is not None and max_sel > 0 and count > max_sel:
                    raise ValueError(
                        f"Modifier group '{g['name']}' allows at most {max_sel} selection(s)"
                    )

        if not chosen:
            return 0.0, None
        total = round(sum(float(m.price_delta or 0) for m in chosen), 2)
        serialized = json.dumps([
            {
                "id": m.id,
                "group_id": m.group_id,
                "name": m.name,
                "name_ar": m.name_ar,
                "price_delta": float(m.price_delta or 0),
            }
            for m in chosen
        ])
        return total, serialized

    @staticmethod
    def _extract_modifier_ids(raw: Any) -> List[int]:
        if not raw:
            return []
        ids: List[int] = []
        for item in raw:
            if isinstance(item, dict):
                val = item.get("id", item.get("modifier_id"))
            else:
                val = item
            if val is not None:
                ids.append(int(val))
        return ids

    @staticmethod
    def _modifier_total(serialized: Optional[str]) -> float:
        """Sum the price deltas off a line's serialized modifier selection."""
        if not serialized:
            return 0.0
        try:
            data = json.loads(serialized)
        except (ValueError, TypeError):
            return 0.0
        if not isinstance(data, list):
            return 0.0
        return round(sum(float(m.get("price_delta") or 0) for m in data if isinstance(m, dict)), 2)

    @staticmethod
    def _normalize_components(raw: Any) -> List[Dict[str, Any]]:
        """Coerce combo components to ``[{product_id, qty}]`` (drops malformed rows)."""
        if not raw:
            return []
        out: List[Dict[str, Any]] = []
        for comp in raw:
            if not isinstance(comp, dict):
                continue
            pid = comp.get("product_id")
            if pid is None:
                continue
            out.append({"product_id": int(pid), "qty": float(comp.get("qty") or 1)})
        return out

    @staticmethod
    def _load_components(combo: Combos) -> List[Dict[str, Any]]:
        try:
            data = json.loads(combo.components) if combo.components else []
        except (ValueError, TypeError):
            return []
        return data if isinstance(data, list) else []

    async def _owned_product(self, product_id: int, user_id: str) -> Optional[Products]:
        result = await self.db.execute(
            select(Products).where(Products.id == product_id, Products.user_id == user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _load_course_state(ticket: OrderTickets) -> Dict[str, Any]:
        try:
            return json.loads(ticket.course_state) if ticket.course_state else {}
        except (ValueError, TypeError):
            return {}
