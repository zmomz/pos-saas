import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy import select, func, update, or_
from sqlalchemy.ext.asyncio import AsyncSession

from models.discounts import Discounts
from services.query_filter import apply_query_filters

# SEC-17: columns a client may filter on via the list endpoint's ?query=.
# ARC-05: ``client_id`` is filterable so list queries can be routed by the tenant
# scope; the service's own ``user_id`` filter still bounds the result, so the
# filter can only narrow within the caller's tenant, never cross it.
FILTERABLE_FIELDS = frozenset({"code", "id", "is_active", "type", "client_id"})

logger = logging.getLogger(__name__)


class DiscountValidationError(ValueError):
    """A discount code failed server-side validation (mapped to HTTP 400).

    Raised by ``DiscountsService.validate`` when a code is unknown, inactive,
    below its ``min_purchase`` floor, outside its validity window, or has
    exhausted its ``max_uses`` cap. PRC-01 requires the server — not the
    client — to make this judgement.
    """


def _as_naive(dt: Optional[datetime]) -> Optional[datetime]:
    """Coerce a datetime to naive wall-clock for comparison.

    The schema stores validity bounds as naive datetimes (SQLite drops the tz,
    matching the ``created_at`` convention), so a tz-aware ``now`` would raise on
    comparison. Dropping ``tzinfo`` keeps both sides comparable without changing
    the wall-clock instant.
    """
    if dt is not None and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def compute_discount_amount(discount: Discounts, subtotal: float) -> float:
    """Server-authoritative discount amount for ``subtotal`` (never client-trusted).

    Percentage discounts apply ``value`` % of the order subtotal; any other type
    (``fixed``/``flat``) applies a flat ``value``. The result is clamped to
    ``[0, subtotal]`` so a discount can never push the order negative (PRC-01).
    """
    value = float(discount.value or 0)
    if (discount.type or "").lower() in ("percentage", "percent", "%"):
        amount = subtotal * (value / 100.0)
    else:  # fixed / flat
        amount = value
    return round(max(0.0, min(amount, subtotal)), 2)


# ------------------ Service Layer ------------------
class DiscountsService:
    """Service layer for Discounts operations"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        data: Dict[str, Any],
        user_id: Optional[str] = None,
        client_id: Optional[int] = None,
    ) -> Optional[Discounts]:
        """Create a new discounts"""
        try:
            if user_id:
                data['user_id'] = user_id
            # ARC-05: stamp the owning merchant's client_id so the row scopes
            # consistently with the core tables. The caller passes the resolved
            # tenant scope's client_id; a payload value is never trusted.
            if client_id is not None:
                data['client_id'] = client_id
            obj = Discounts(**data)
            self.db.add(obj)
            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Created discounts with id: {obj.id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating discounts: {str(e)}")
            raise

    async def check_ownership(self, obj_id: int, user_id: str) -> bool:
        """Check if user owns this record.

        A missing record — or one owned by another tenant — is a legitimate
        authorization answer of ``False``. A DB/infrastructure error is *not*:
        ``get_by_id`` logs and re-raises it so the caller fails closed rather
        than mistaking an infra fault for "not the owner" (ARC-10).
        """
        obj = await self.get_by_id(obj_id, user_id=user_id)
        return obj is not None

    async def get_by_id(self, obj_id: int, user_id: Optional[str] = None) -> Optional[Discounts]:
        """Get discounts by ID (user can only see their own records)"""
        try:
            query = select(Discounts).where(Discounts.id == obj_id)
            if user_id:
                query = query.where(Discounts.user_id == user_id)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching discounts {obj_id}: {str(e)}")
            raise

    async def get_list(
        self, 
        skip: int = 0, 
        limit: int = 20, 
        user_id: Optional[str] = None,
        query_dict: Optional[Dict[str, Any]] = None,
        sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get paginated list of discountss (user can only see their own records)"""
        try:
            query = select(Discounts)
            count_query = select(func.count(Discounts.id))
            
            if user_id:
                query = query.where(Discounts.user_id == user_id)
                count_query = count_query.where(Discounts.user_id == user_id)
            
            query, count_query = apply_query_filters(
                Discounts, query, count_query, query_dict, FILTERABLE_FIELDS
            )
            
            count_result = await self.db.execute(count_query)
            total = count_result.scalar()

            if sort:
                if sort.startswith('-'):
                    field_name = sort[1:]
                    if hasattr(Discounts, field_name):
                        query = query.order_by(getattr(Discounts, field_name).desc())
                else:
                    if hasattr(Discounts, sort):
                        query = query.order_by(getattr(Discounts, sort))
            else:
                query = query.order_by(Discounts.id.desc())

            result = await self.db.execute(query.offset(skip).limit(limit))
            items = result.scalars().all()

            return {
                "items": items,
                "total": total,
                "skip": skip,
                "limit": limit,
            }
        except Exception as e:
            logger.error(f"Error fetching discounts list: {str(e)}")
            raise

    async def update(self, obj_id: int, update_data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Discounts]:
        """Update discounts (requires ownership)"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            if not obj:
                logger.warning(f"Discounts {obj_id} not found for update")
                return None
            for key, value in update_data.items():
                if hasattr(obj, key) and key != 'user_id':
                    setattr(obj, key, value)

            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Updated discounts {obj_id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating discounts {obj_id}: {str(e)}")
            raise

    async def delete(self, obj_id: int, user_id: Optional[str] = None) -> bool:
        """Delete discounts (requires ownership)"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            if not obj:
                logger.warning(f"Discounts {obj_id} not found for deletion")
                return False
            await self.db.delete(obj)
            await self.db.commit()
            logger.info(f"Deleted discounts {obj_id}")
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting discounts {obj_id}: {str(e)}")
            raise

    async def get_by_code(self, code: str, user_id: str) -> Optional[Discounts]:
        """Look up a discount by code within the owner's scope (case-insensitive)."""
        try:
            result = await self.db.execute(
                select(Discounts).where(
                    func.lower(Discounts.code) == (code or "").strip().lower(),
                    Discounts.user_id == str(user_id),
                )
            )
            return result.scalars().first()
        except Exception as e:
            logger.error(f"Error fetching discount by code: {str(e)}")
            raise

    async def validate(
        self,
        code: str,
        subtotal: float,
        user_id: str,
        now: Optional[datetime] = None,
    ) -> Discounts:
        """Validate a discount code for an order subtotal (PRC-01/PRC-02). Read-only.

        Enforces, server-side: the code exists in the caller's scope, is active,
        falls inside its scheduled validity window (PRC-02 time-window promos),
        the order meets ``min_purchase``, and the ``max_uses`` cap is not already
        exhausted. Raises ``DiscountValidationError`` (→ HTTP 400) otherwise.
        Does **not** consume a use — call ``consume`` for that, atomically with
        the sale, so a rolled-back sale never spends a use.

        ``now`` is injectable so the window check is deterministic in tests; it
        defaults to the server wall-clock (naive, matching the stored bounds).
        """
        discount = await self.get_by_code(code, user_id)
        if not discount:
            raise DiscountValidationError("Invalid discount code")
        if discount.is_active is False:
            raise DiscountValidationError("This discount is no longer active")
        # PRC-02: honour the scheduled validity window. A code with a future
        # ``starts_at`` is not yet live (a scheduled promo); one past its
        # ``ends_at`` has expired. Either bound NULL ⇒ open-ended on that side.
        reference = _as_naive(now) if now is not None else datetime.now()
        starts_at = _as_naive(discount.starts_at)
        ends_at = _as_naive(discount.ends_at)
        if starts_at is not None and reference < starts_at:
            raise DiscountValidationError("This discount is not active yet")
        if ends_at is not None and reference > ends_at:
            raise DiscountValidationError("This discount has expired")
        if discount.min_purchase and float(subtotal) < float(discount.min_purchase):
            raise DiscountValidationError(
                f"Minimum purchase of {float(discount.min_purchase):.2f} required"
            )
        if discount.max_uses is not None and (discount.usage_count or 0) >= discount.max_uses:
            raise DiscountValidationError("This discount has reached its usage limit")
        return discount

    async def consume(self, discount_id: int, user_id: str) -> bool:
        """Atomically increment ``usage_count`` enforcing the cap. No commit.

        Issues a single conditional UPDATE that increments only while the cap is
        not yet reached, so concurrent sales cannot push ``usage_count`` past
        ``max_uses`` (the cap is enforced in SQL, not by a read-then-write race).
        Runs inside the caller's transaction (the sale), so the increment commits
        with the sale and rolls back if the sale fails. Returns ``True`` when a
        use was consumed, ``False`` when the cap was already exhausted.
        """
        try:
            result = await self.db.execute(
                update(Discounts)
                .where(
                    Discounts.id == discount_id,
                    Discounts.user_id == str(user_id),
                    or_(
                        Discounts.max_uses.is_(None),
                        func.coalesce(Discounts.usage_count, 0) < Discounts.max_uses,
                    ),
                )
                .values(usage_count=func.coalesce(Discounts.usage_count, 0) + 1)
            )
            return (result.rowcount or 0) > 0
        except Exception as e:
            logger.error(f"Error consuming discount {discount_id}: {str(e)}")
            raise

    async def get_by_field(self, field_name: str, field_value: Any) -> Optional[Discounts]:
        """Get discounts by any field"""
        try:
            if not hasattr(Discounts, field_name):
                raise ValueError(f"Field {field_name} does not exist on Discounts")
            result = await self.db.execute(
                select(Discounts).where(getattr(Discounts, field_name) == field_value)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching discounts by {field_name}: {str(e)}")
            raise

    async def list_by_field(
        self, field_name: str, field_value: Any, skip: int = 0, limit: int = 20
    ) -> List[Discounts]:
        """Get list of discountss filtered by field"""
        try:
            if not hasattr(Discounts, field_name):
                raise ValueError(f"Field {field_name} does not exist on Discounts")
            result = await self.db.execute(
                select(Discounts)
                .where(getattr(Discounts, field_name) == field_value)
                .offset(skip)
                .limit(limit)
                .order_by(Discounts.id.desc())
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error fetching discountss by {field_name}: {str(e)}")
            raise