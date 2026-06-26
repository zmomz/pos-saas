import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Iterable, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.loyalty_points import Loyalty_points

logger = logging.getLogger(__name__)

# Ledger entry types that add points (a "credit"/lot) vs. spend them (a "debit").
CREDIT_TYPES = frozenset({"earned", "add"})
DEBIT_TYPES = frozenset({"redeemed", "deduct"})


def compute_usable_balance(
    entries: Iterable[Dict[str, Any]],
    expiry_days: int = 0,
    now: Optional[datetime] = None,
) -> int:
    """Usable point balance from a customer's ledger, aging out expired credits.

    ``entries`` is an iterable of ledger movements, each a mapping with ``type``
    (one of earned/add/redeemed/deduct), ``points`` (positive magnitude) and
    ``created_at`` (a ``datetime``). They are processed oldest-first.

    Each credit forms a dated *lot*; debits consume the oldest lots first (FIFO),
    mirroring how points-programs spend the points closest to expiring. A lot
    whose ``created_at`` is older than ``expiry_days`` contributes nothing to the
    usable balance. ``expiry_days`` of 0 (or falsy) means points never expire.

    This is the canonical balance the admin "balances" view surfaces and the
    redeem path could guard against — derived purely from the ledger so it is
    auditable (AC1) and ages out (AC2).
    """
    ordered = sorted(entries, key=lambda e: (e["created_at"] is None, e["created_at"]))
    lots: List[List[Any]] = []  # each [created_at, remaining_points]
    for entry in ordered:
        etype = entry["type"]
        points = entry["points"] or 0
        if etype in CREDIT_TYPES:
            lots.append([entry["created_at"], points])
        elif etype in DEBIT_TYPES:
            need = points
            for lot in lots:
                if need <= 0:
                    break
                take = min(lot[1], need)
                lot[1] -= take
                need -= take

    if expiry_days and expiry_days > 0:
        now = now or datetime.now()
        cutoff = now - timedelta(days=expiry_days)
        return sum(rem for created, rem in lots if created is not None and created >= cutoff)
    return sum(rem for _, rem in lots)


# ------------------ Service Layer ------------------
class Loyalty_pointsService:
    """Service layer for Loyalty_points operations"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Loyalty_points]:
        """Create a new loyalty_points"""
        try:
            if user_id:
                data['user_id'] = user_id
            obj = Loyalty_points(**data)
            self.db.add(obj)
            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Created loyalty_points with id: {obj.id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating loyalty_points: {str(e)}")
            raise

    async def check_ownership(self, obj_id: int, user_id: str) -> bool:
        """Check if user owns this record"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            return obj is not None
        except Exception as e:
            logger.error(f"Error checking ownership for loyalty_points {obj_id}: {str(e)}")
            return False

    async def get_by_id(self, obj_id: int, user_id: Optional[str] = None) -> Optional[Loyalty_points]:
        """Get loyalty_points by ID (user can only see their own records)"""
        try:
            query = select(Loyalty_points).where(Loyalty_points.id == obj_id)
            if user_id:
                query = query.where(Loyalty_points.user_id == user_id)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching loyalty_points {obj_id}: {str(e)}")
            raise

    async def get_list(
        self, 
        skip: int = 0, 
        limit: int = 20, 
        user_id: Optional[str] = None,
        query_dict: Optional[Dict[str, Any]] = None,
        sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get paginated list of loyalty_pointss (user can only see their own records)"""
        try:
            query = select(Loyalty_points)
            count_query = select(func.count(Loyalty_points.id))
            
            if user_id:
                query = query.where(Loyalty_points.user_id == user_id)
                count_query = count_query.where(Loyalty_points.user_id == user_id)
            
            if query_dict:
                for field, value in query_dict.items():
                    if hasattr(Loyalty_points, field):
                        query = query.where(getattr(Loyalty_points, field) == value)
                        count_query = count_query.where(getattr(Loyalty_points, field) == value)
            
            count_result = await self.db.execute(count_query)
            total = count_result.scalar()

            if sort:
                if sort.startswith('-'):
                    field_name = sort[1:]
                    if hasattr(Loyalty_points, field_name):
                        query = query.order_by(getattr(Loyalty_points, field_name).desc())
                else:
                    if hasattr(Loyalty_points, sort):
                        query = query.order_by(getattr(Loyalty_points, sort))
            else:
                query = query.order_by(Loyalty_points.id.desc())

            result = await self.db.execute(query.offset(skip).limit(limit))
            items = result.scalars().all()

            return {
                "items": items,
                "total": total,
                "skip": skip,
                "limit": limit,
            }
        except Exception as e:
            logger.error(f"Error fetching loyalty_points list: {str(e)}")
            raise

    # The point balance is owned by the loyalty ledger (loyalty_transactions):
    # every movement flows through services.loyalty.record_ledger_movement so the
    # balance and the ledger stay in lock-step (FIN-08). The generic CRUD PUT must
    # not move a balance behind the ledger's back, so these fields are read-only here.
    _LEDGER_OWNED_FIELDS = frozenset({"points_balance", "total_earned", "total_redeemed"})

    async def update(self, obj_id: int, update_data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Loyalty_points]:
        """Update loyalty_points (requires ownership).

        Balance-bearing fields are ignored: a points change must go through the
        loyalty service so it leaves exactly one ledger row (FIN-08).
        """
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            if not obj:
                logger.warning(f"Loyalty_points {obj_id} not found for update")
                return None
            for key, value in update_data.items():
                if key in self._LEDGER_OWNED_FIELDS:
                    continue
                if hasattr(obj, key) and key != 'user_id':
                    setattr(obj, key, value)

            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Updated loyalty_points {obj_id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating loyalty_points {obj_id}: {str(e)}")
            raise

    async def delete(self, obj_id: int, user_id: Optional[str] = None) -> bool:
        """Delete loyalty_points (requires ownership)"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            if not obj:
                logger.warning(f"Loyalty_points {obj_id} not found for deletion")
                return False
            await self.db.delete(obj)
            await self.db.commit()
            logger.info(f"Deleted loyalty_points {obj_id}")
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting loyalty_points {obj_id}: {str(e)}")
            raise

    async def get_by_field(self, field_name: str, field_value: Any) -> Optional[Loyalty_points]:
        """Get loyalty_points by any field"""
        try:
            if not hasattr(Loyalty_points, field_name):
                raise ValueError(f"Field {field_name} does not exist on Loyalty_points")
            result = await self.db.execute(
                select(Loyalty_points).where(getattr(Loyalty_points, field_name) == field_value)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching loyalty_points by {field_name}: {str(e)}")
            raise

    async def list_by_field(
        self, field_name: str, field_value: Any, skip: int = 0, limit: int = 20
    ) -> List[Loyalty_points]:
        """Get list of loyalty_pointss filtered by field"""
        try:
            if not hasattr(Loyalty_points, field_name):
                raise ValueError(f"Field {field_name} does not exist on Loyalty_points")
            result = await self.db.execute(
                select(Loyalty_points)
                .where(getattr(Loyalty_points, field_name) == field_value)
                .offset(skip)
                .limit(limit)
                .order_by(Loyalty_points.id.desc())
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error fetching loyalty_pointss by {field_name}: {str(e)}")
            raise