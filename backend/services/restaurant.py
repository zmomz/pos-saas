"""Service layer for restaurant floor/table/order-ticket operations (F-045).

All operations are scoped to ``user_id`` (the merchant's own account) so one
client can never read or mutate another client's floor — the same ownership
invariant the generic entity triad enforces (SEC-02). State transitions
(opening an order, freeing a table) are committed atomically.
"""
import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.products import Products
from models.restaurant import (
    FloorZones,
    OrderTicketItems,
    OrderTickets,
    RestaurantTables,
)

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
# Statuses past which a ticket can no longer be edited from the floor.
CLOSED_TICKET_STATUSES = ("settled", "void")


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

        unit_price = data.get("unit_price")
        if unit_price is None:
            unit_price = float(product.price) if product is not None else 0.0
        unit_price = round(float(unit_price), 2)

        name = data.get("name") or (product.name if product is not None else None)
        modifiers = data.get("modifiers")
        if modifiers is not None and not isinstance(modifiers, str):
            modifiers = json.dumps(modifiers)

        try:
            item = OrderTicketItems(
                user_id=user_id,
                client_id=client_id,
                ticket_id=ticket.id,
                product_id=product_id,
                variant_id=data.get("variant_id"),
                name=name,
                qty=qty,
                unit_price=unit_price,
                line_total=round(qty * unit_price, 2),
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
            item.line_total = round(item.qty * item.unit_price, 2)
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
            await self.db.commit()
            fired_ids = [line.id for line in target]
            logger.info(f"Fired course '{course}' on ticket {ticket_id}: {len(fired_ids)} line(s)")
            return {"ticket_id": ticket_id, "course": course, "fired_item_ids": fired_ids, "fired_count": len(fired_ids)}
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
        items = [i for i in await self.list_items(ticket_id, user_id)]
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

    # ----------------------------------------------------------------- helpers
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
