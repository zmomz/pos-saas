import logging
from typing import Optional, Dict, Any, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.webhooks import Webhooks
from services.query_filter import apply_query_filters

# SEC-17: columns a client may filter on via the list endpoint's ?query=.
FILTERABLE_FIELDS = frozenset({"client_id", "id", "is_active", "name"})

logger = logging.getLogger(__name__)


# ------------------ Service Layer ------------------
class WebhooksService:
    """Service layer for Webhooks operations"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Webhooks]:
        """Create a new webhooks"""
        try:
            if user_id:
                data['user_id'] = user_id
            obj = Webhooks(**data)
            self.db.add(obj)
            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Created webhooks with id: {obj.id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating webhooks: {str(e)}")
            raise

    async def check_ownership(self, obj_id: int, user_id: str) -> bool:
        """Check if user owns this record"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            return obj is not None
        except Exception as e:
            logger.error(f"Error checking ownership for webhooks {obj_id}: {str(e)}")
            return False

    async def get_by_id(self, obj_id: int, user_id: Optional[str] = None) -> Optional[Webhooks]:
        """Get webhooks by ID (user can only see their own records)"""
        try:
            query = select(Webhooks).where(Webhooks.id == obj_id)
            if user_id:
                query = query.where(Webhooks.user_id == user_id)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching webhooks {obj_id}: {str(e)}")
            raise

    async def get_list(
        self, 
        skip: int = 0, 
        limit: int = 20, 
        user_id: Optional[str] = None,
        query_dict: Optional[Dict[str, Any]] = None,
        sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get paginated list of webhookss (user can only see their own records)"""
        try:
            query = select(Webhooks)
            count_query = select(func.count(Webhooks.id))
            
            if user_id:
                query = query.where(Webhooks.user_id == user_id)
                count_query = count_query.where(Webhooks.user_id == user_id)
            
            query, count_query = apply_query_filters(
                Webhooks, query, count_query, query_dict, FILTERABLE_FIELDS
            )
            
            count_result = await self.db.execute(count_query)
            total = count_result.scalar()

            if sort:
                if sort.startswith('-'):
                    field_name = sort[1:]
                    if hasattr(Webhooks, field_name):
                        query = query.order_by(getattr(Webhooks, field_name).desc())
                else:
                    if hasattr(Webhooks, sort):
                        query = query.order_by(getattr(Webhooks, sort))
            else:
                query = query.order_by(Webhooks.id.desc())

            result = await self.db.execute(query.offset(skip).limit(limit))
            items = result.scalars().all()

            return {
                "items": items,
                "total": total,
                "skip": skip,
                "limit": limit,
            }
        except Exception as e:
            logger.error(f"Error fetching webhooks list: {str(e)}")
            raise

    async def update(self, obj_id: int, update_data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Webhooks]:
        """Update webhooks (requires ownership)"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            if not obj:
                logger.warning(f"Webhooks {obj_id} not found for update")
                return None
            for key, value in update_data.items():
                if hasattr(obj, key) and key != 'user_id':
                    setattr(obj, key, value)

            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Updated webhooks {obj_id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating webhooks {obj_id}: {str(e)}")
            raise

    async def delete(self, obj_id: int, user_id: Optional[str] = None) -> bool:
        """Delete webhooks (requires ownership)"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            if not obj:
                logger.warning(f"Webhooks {obj_id} not found for deletion")
                return False
            await self.db.delete(obj)
            await self.db.commit()
            logger.info(f"Deleted webhooks {obj_id}")
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting webhooks {obj_id}: {str(e)}")
            raise

    async def get_by_field(self, field_name: str, field_value: Any) -> Optional[Webhooks]:
        """Get webhooks by any field"""
        try:
            if not hasattr(Webhooks, field_name):
                raise ValueError(f"Field {field_name} does not exist on Webhooks")
            result = await self.db.execute(
                select(Webhooks).where(getattr(Webhooks, field_name) == field_value)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching webhooks by {field_name}: {str(e)}")
            raise

    async def list_by_field(
        self, field_name: str, field_value: Any, skip: int = 0, limit: int = 20
    ) -> List[Webhooks]:
        """Get list of webhookss filtered by field"""
        try:
            if not hasattr(Webhooks, field_name):
                raise ValueError(f"Field {field_name} does not exist on Webhooks")
            result = await self.db.execute(
                select(Webhooks)
                .where(getattr(Webhooks, field_name) == field_value)
                .offset(skip)
                .limit(limit)
                .order_by(Webhooks.id.desc())
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error fetching webhookss by {field_name}: {str(e)}")
            raise