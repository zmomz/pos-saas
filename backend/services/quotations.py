import logging
from typing import Optional, Dict, Any, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.quotations import Quotations
from services.query_filter import apply_query_filters

# SEC-17: columns a client may filter on via the list endpoint's ?query=.
FILTERABLE_FIELDS = frozenset({"client_id", "converted_transaction_id", "id", "quote_number", "status"})

logger = logging.getLogger(__name__)


# ------------------ Service Layer ------------------
class QuotationsService:
    """Service layer for Quotations operations"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Quotations]:
        """Create a new quotations"""
        try:
            if user_id:
                data['user_id'] = user_id
            obj = Quotations(**data)
            self.db.add(obj)
            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Created quotations with id: {obj.id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating quotations: {str(e)}")
            raise

    async def check_ownership(self, obj_id: int, user_id: str) -> bool:
        """Check if user owns this record"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            return obj is not None
        except Exception as e:
            logger.error(f"Error checking ownership for quotations {obj_id}: {str(e)}")
            return False

    async def get_by_id(self, obj_id: int, user_id: Optional[str] = None) -> Optional[Quotations]:
        """Get quotations by ID (user can only see their own records)"""
        try:
            query = select(Quotations).where(Quotations.id == obj_id)
            if user_id:
                query = query.where(Quotations.user_id == user_id)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching quotations {obj_id}: {str(e)}")
            raise

    async def get_list(
        self,
        skip: int = 0,
        limit: int = 20,
        user_id: Optional[str] = None,
        query_dict: Optional[Dict[str, Any]] = None,
        sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get paginated list of quotationss (user can only see their own records)"""
        try:
            query = select(Quotations)
            count_query = select(func.count(Quotations.id))

            if user_id:
                query = query.where(Quotations.user_id == user_id)
                count_query = count_query.where(Quotations.user_id == user_id)

            query, count_query = apply_query_filters(
                Quotations, query, count_query, query_dict, FILTERABLE_FIELDS
            )

            count_result = await self.db.execute(count_query)
            total = count_result.scalar()

            if sort:
                if sort.startswith('-'):
                    field_name = sort[1:]
                    if hasattr(Quotations, field_name):
                        query = query.order_by(getattr(Quotations, field_name).desc())
                else:
                    if hasattr(Quotations, sort):
                        query = query.order_by(getattr(Quotations, sort))
            else:
                query = query.order_by(Quotations.id.desc())

            result = await self.db.execute(query.offset(skip).limit(limit))
            items = result.scalars().all()

            return {
                "items": items,
                "total": total,
                "skip": skip,
                "limit": limit,
            }
        except Exception as e:
            logger.error(f"Error fetching quotations list: {str(e)}")
            raise

    async def update(self, obj_id: int, update_data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Quotations]:
        """Update quotations (requires ownership)"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            if not obj:
                logger.warning(f"Quotations {obj_id} not found for update")
                return None
            for key, value in update_data.items():
                if hasattr(obj, key) and key != 'user_id':
                    setattr(obj, key, value)

            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Updated quotations {obj_id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating quotations {obj_id}: {str(e)}")
            raise

    async def delete(self, obj_id: int, user_id: Optional[str] = None) -> bool:
        """Delete quotations (requires ownership)"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            if not obj:
                logger.warning(f"Quotations {obj_id} not found for deletion")
                return False
            await self.db.delete(obj)
            await self.db.commit()
            logger.info(f"Deleted quotations {obj_id}")
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting quotations {obj_id}: {str(e)}")
            raise

    async def get_by_field(self, field_name: str, field_value: Any) -> Optional[Quotations]:
        """Get quotations by any field"""
        try:
            if not hasattr(Quotations, field_name):
                raise ValueError(f"Field {field_name} does not exist on Quotations")
            result = await self.db.execute(
                select(Quotations).where(getattr(Quotations, field_name) == field_value)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching quotations by {field_name}: {str(e)}")
            raise

    async def list_by_field(
        self, field_name: str, field_value: Any, skip: int = 0, limit: int = 20
    ) -> List[Quotations]:
        """Get list of quotationss filtered by field"""
        try:
            if not hasattr(Quotations, field_name):
                raise ValueError(f"Field {field_name} does not exist on Quotations")
            result = await self.db.execute(
                select(Quotations)
                .where(getattr(Quotations, field_name) == field_value)
                .offset(skip)
                .limit(limit)
                .order_by(Quotations.id.desc())
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error fetching quotationss by {field_name}: {str(e)}")
            raise
