"""Service layer for restaurant floor/table/order-ticket operations (F-045).

All operations are scoped to ``user_id`` (the merchant's own account) so one
client can never read or mutate another client's floor — the same ownership
invariant the generic entity triad enforces (SEC-02). State transitions
(opening an order, freeing a table) are committed atomically.
"""
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.restaurant import FloorZones, OrderTickets, RestaurantTables

logger = logging.getLogger(__name__)

# Allowed enum values (mirrors models.restaurant docstring).
TABLE_STATES = ("free", "occupied", "bill_printed")
ORDER_TYPES = ("dine_in", "takeaway", "delivery")
TICKET_STATUSES = ("open", "held", "fired", "settled", "void")


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
