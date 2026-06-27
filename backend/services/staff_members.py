import logging
from typing import Optional, Dict, Any, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.staff_members import Staff_members
from services.query_filter import apply_query_filters

# SEC-17: columns a client may filter on via the list endpoint's ?query=.
FILTERABLE_FIELDS = frozenset({"email", "id", "is_active", "login_user_id", "role"})

logger = logging.getLogger(__name__)


# ------------------ Service Layer ------------------
class Staff_membersService:
    """Service layer for Staff_members operations"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Staff_members]:
        """Create a new staff_members"""
        try:
            if user_id:
                data['user_id'] = user_id
            obj = Staff_members(**data)
            self.db.add(obj)
            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Created staff_members with id: {obj.id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating staff_members: {str(e)}")
            raise

    async def check_ownership(self, obj_id: int, user_id: str) -> bool:
        """Check if user owns this record"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            return obj is not None
        except Exception as e:
            logger.error(f"Error checking ownership for staff_members {obj_id}: {str(e)}")
            return False

    async def get_by_id(self, obj_id: int, user_id: Optional[str] = None) -> Optional[Staff_members]:
        """Get staff_members by ID (user can only see their own records)"""
        try:
            query = select(Staff_members).where(Staff_members.id == obj_id)
            if user_id:
                query = query.where(Staff_members.user_id == user_id)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching staff_members {obj_id}: {str(e)}")
            raise

    async def get_list(
        self, 
        skip: int = 0, 
        limit: int = 20, 
        user_id: Optional[str] = None,
        query_dict: Optional[Dict[str, Any]] = None,
        sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get paginated list of staff_memberss (user can only see their own records)"""
        try:
            query = select(Staff_members)
            count_query = select(func.count(Staff_members.id))
            
            if user_id:
                query = query.where(Staff_members.user_id == user_id)
                count_query = count_query.where(Staff_members.user_id == user_id)
            
            query, count_query = apply_query_filters(
                Staff_members, query, count_query, query_dict, FILTERABLE_FIELDS
            )
            
            count_result = await self.db.execute(count_query)
            total = count_result.scalar()

            if sort:
                if sort.startswith('-'):
                    field_name = sort[1:]
                    if hasattr(Staff_members, field_name):
                        query = query.order_by(getattr(Staff_members, field_name).desc())
                else:
                    if hasattr(Staff_members, sort):
                        query = query.order_by(getattr(Staff_members, sort))
            else:
                query = query.order_by(Staff_members.id.desc())

            result = await self.db.execute(query.offset(skip).limit(limit))
            items = result.scalars().all()

            return {
                "items": items,
                "total": total,
                "skip": skip,
                "limit": limit,
            }
        except Exception as e:
            logger.error(f"Error fetching staff_members list: {str(e)}")
            raise

    async def update(self, obj_id: int, update_data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Staff_members]:
        """Update staff_members (requires ownership)"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            if not obj:
                logger.warning(f"Staff_members {obj_id} not found for update")
                return None
            for key, value in update_data.items():
                if hasattr(obj, key) and key != 'user_id':
                    setattr(obj, key, value)

            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Updated staff_members {obj_id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating staff_members {obj_id}: {str(e)}")
            raise

    async def delete(self, obj_id: int, user_id: Optional[str] = None) -> bool:
        """Delete staff_members (requires ownership)"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            if not obj:
                logger.warning(f"Staff_members {obj_id} not found for deletion")
                return False
            await self.db.delete(obj)
            await self.db.commit()
            logger.info(f"Deleted staff_members {obj_id}")
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting staff_members {obj_id}: {str(e)}")
            raise

    async def get_by_field(self, field_name: str, field_value: Any) -> Optional[Staff_members]:
        """Get staff_members by any field"""
        try:
            if not hasattr(Staff_members, field_name):
                raise ValueError(f"Field {field_name} does not exist on Staff_members")
            result = await self.db.execute(
                select(Staff_members).where(getattr(Staff_members, field_name) == field_value)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching staff_members by {field_name}: {str(e)}")
            raise

    async def list_by_field(
        self, field_name: str, field_value: Any, skip: int = 0, limit: int = 20
    ) -> List[Staff_members]:
        """Get list of staff_memberss filtered by field"""
        try:
            if not hasattr(Staff_members, field_name):
                raise ValueError(f"Field {field_name} does not exist on Staff_members")
            result = await self.db.execute(
                select(Staff_members)
                .where(getattr(Staff_members, field_name) == field_value)
                .offset(skip)
                .limit(limit)
                .order_by(Staff_members.id.desc())
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error fetching staff_memberss by {field_name}: {str(e)}")
            raise