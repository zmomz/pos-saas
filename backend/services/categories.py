import logging
from typing import Optional, Dict, Any, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.categories import Categories
from services.query_filter import apply_query_filters

# SEC-17: columns a client may filter on via the list endpoint's ?query=.
# ARC-05 / ISSUE-193: ``client_id`` is *advisory* — an optional within-tenant
# narrowing filter, not the isolation boundary. The service's own ``user_id``
# filter still bounds every result, so a client_id filter can only narrow within
# the caller's tenant, never cross it. See dependencies.tenancy.TenantScope.
FILTERABLE_FIELDS = frozenset({"id", "name", "parent_id", "client_id"})

logger = logging.getLogger(__name__)


# ------------------ Service Layer ------------------
class CategoriesService:
    """Service layer for Categories operations"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        data: Dict[str, Any],
        user_id: Optional[str] = None,
        client_id: Optional[int] = None,
    ) -> Optional[Categories]:
        """Create a new categories"""
        try:
            if user_id:
                data['user_id'] = user_id
            # ARC-05 / ISSUE-193: stamp the owning merchant's client_id as advisory
            # metadata, for parity with the core tables — isolation stays bounded by
            # user_id, not this column. The caller passes the resolved tenant scope's
            # client_id; a payload value is never trusted.
            if client_id is not None:
                data['client_id'] = client_id
            obj = Categories(**data)
            self.db.add(obj)
            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Created categories with id: {obj.id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating categories: {str(e)}")
            raise

    async def check_ownership(self, obj_id: int, user_id: str) -> bool:
        """Check if user owns this record"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            return obj is not None
        except Exception as e:
            logger.error(f"Error checking ownership for categories {obj_id}: {str(e)}")
            return False

    async def get_by_id(self, obj_id: int, user_id: Optional[str] = None) -> Optional[Categories]:
        """Get categories by ID (user can only see their own records)"""
        try:
            query = select(Categories).where(Categories.id == obj_id)
            if user_id:
                query = query.where(Categories.user_id == user_id)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching categories {obj_id}: {str(e)}")
            raise

    async def get_list(
        self, 
        skip: int = 0, 
        limit: int = 20, 
        user_id: Optional[str] = None,
        query_dict: Optional[Dict[str, Any]] = None,
        sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get paginated list of categoriess (user can only see their own records)"""
        try:
            query = select(Categories)
            count_query = select(func.count(Categories.id))
            
            if user_id:
                query = query.where(Categories.user_id == user_id)
                count_query = count_query.where(Categories.user_id == user_id)
            
            query, count_query = apply_query_filters(
                Categories, query, count_query, query_dict, FILTERABLE_FIELDS
            )
            
            count_result = await self.db.execute(count_query)
            total = count_result.scalar()

            if sort:
                if sort.startswith('-'):
                    field_name = sort[1:]
                    if hasattr(Categories, field_name):
                        query = query.order_by(getattr(Categories, field_name).desc())
                else:
                    if hasattr(Categories, sort):
                        query = query.order_by(getattr(Categories, sort))
            else:
                query = query.order_by(Categories.id.desc())

            result = await self.db.execute(query.offset(skip).limit(limit))
            items = result.scalars().all()

            return {
                "items": items,
                "total": total,
                "skip": skip,
                "limit": limit,
            }
        except Exception as e:
            logger.error(f"Error fetching categories list: {str(e)}")
            raise

    async def update(self, obj_id: int, update_data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Categories]:
        """Update categories (requires ownership)"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            if not obj:
                logger.warning(f"Categories {obj_id} not found for update")
                return None
            for key, value in update_data.items():
                if hasattr(obj, key) and key != 'user_id':
                    setattr(obj, key, value)

            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Updated categories {obj_id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating categories {obj_id}: {str(e)}")
            raise

    async def delete(self, obj_id: int, user_id: Optional[str] = None) -> bool:
        """Delete categories (requires ownership)"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            if not obj:
                logger.warning(f"Categories {obj_id} not found for deletion")
                return False
            await self.db.delete(obj)
            await self.db.commit()
            logger.info(f"Deleted categories {obj_id}")
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting categories {obj_id}: {str(e)}")
            raise

    async def get_by_field(self, field_name: str, field_value: Any) -> Optional[Categories]:
        """Get categories by any field"""
        try:
            if not hasattr(Categories, field_name):
                raise ValueError(f"Field {field_name} does not exist on Categories")
            result = await self.db.execute(
                select(Categories).where(getattr(Categories, field_name) == field_value)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching categories by {field_name}: {str(e)}")
            raise

    async def list_by_field(
        self, field_name: str, field_value: Any, skip: int = 0, limit: int = 20
    ) -> List[Categories]:
        """Get list of categoriess filtered by field"""
        try:
            if not hasattr(Categories, field_name):
                raise ValueError(f"Field {field_name} does not exist on Categories")
            result = await self.db.execute(
                select(Categories)
                .where(getattr(Categories, field_name) == field_value)
                .offset(skip)
                .limit(limit)
                .order_by(Categories.id.desc())
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error fetching categoriess by {field_name}: {str(e)}")
            raise