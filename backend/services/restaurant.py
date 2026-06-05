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
    Combos,
    FloorZones,
    Modifiers,
    ModifierGroups,
    OrderTicketItems,
    OrderTickets,
    ProductModifierGroups,
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
