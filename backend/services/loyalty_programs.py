import logging
from typing import Optional, Dict, Any, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.loyalty_programs import Loyalty_programs
from services.loyalty import enforce_single_active_program

logger = logging.getLogger(__name__)


# ------------------ Service Layer ------------------
class Loyalty_programsService:
    """Service layer for Loyalty_programs operations"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Loyalty_programs]:
        """Create a new loyalty_programs"""
        try:
            if user_id:
                data['user_id'] = user_id
            obj = Loyalty_programs(**data)
            self.db.add(obj)
            await self.db.flush()
            # Single authoritative active program per tenant (FIN-11): a new
            # active program deactivates any other active one for this tenant.
            if obj.is_active:
                await enforce_single_active_program(self.db, obj.user_id, obj.id)
            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Created loyalty_programs with id: {obj.id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating loyalty_programs: {str(e)}")
            raise

    async def check_ownership(self, obj_id: int, user_id: str) -> bool:
        """Check if user owns this record"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            return obj is not None
        except Exception as e:
            logger.error(f"Error checking ownership for loyalty_programs {obj_id}: {str(e)}")
            return False

    async def get_by_id(self, obj_id: int, user_id: Optional[str] = None) -> Optional[Loyalty_programs]:
        """Get loyalty_programs by ID (user can only see their own records)"""
        try:
            query = select(Loyalty_programs).where(Loyalty_programs.id == obj_id)
            if user_id:
                query = query.where(Loyalty_programs.user_id == user_id)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching loyalty_programs {obj_id}: {str(e)}")
            raise

    async def get_list(
        self, 
        skip: int = 0, 
        limit: int = 20, 
        user_id: Optional[str] = None,
        query_dict: Optional[Dict[str, Any]] = None,
        sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get paginated list of loyalty_programss (user can only see their own records)"""
        try:
            query = select(Loyalty_programs)
            count_query = select(func.count(Loyalty_programs.id))
            
            if user_id:
                query = query.where(Loyalty_programs.user_id == user_id)
                count_query = count_query.where(Loyalty_programs.user_id == user_id)
            
            if query_dict:
                for field, value in query_dict.items():
                    if hasattr(Loyalty_programs, field):
                        query = query.where(getattr(Loyalty_programs, field) == value)
                        count_query = count_query.where(getattr(Loyalty_programs, field) == value)
            
            count_result = await self.db.execute(count_query)
            total = count_result.scalar()

            if sort:
                if sort.startswith('-'):
                    field_name = sort[1:]
                    if hasattr(Loyalty_programs, field_name):
                        query = query.order_by(getattr(Loyalty_programs, field_name).desc())
                else:
                    if hasattr(Loyalty_programs, sort):
                        query = query.order_by(getattr(Loyalty_programs, sort))
            else:
                query = query.order_by(Loyalty_programs.id.desc())

            result = await self.db.execute(query.offset(skip).limit(limit))
            items = result.scalars().all()

            return {
                "items": items,
                "total": total,
                "skip": skip,
                "limit": limit,
            }
        except Exception as e:
            logger.error(f"Error fetching loyalty_programs list: {str(e)}")
            raise

    async def update(self, obj_id: int, update_data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Loyalty_programs]:
        """Update loyalty_programs (requires ownership)"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            if not obj:
                logger.warning(f"Loyalty_programs {obj_id} not found for update")
                return None
            for key, value in update_data.items():
                if hasattr(obj, key) and key != 'user_id':
                    setattr(obj, key, value)

            await self.db.flush()
            # Single authoritative active program per tenant (FIN-11): flipping a
            # program active deactivates any other active one for this tenant.
            if obj.is_active:
                await enforce_single_active_program(self.db, obj.user_id, obj.id)
            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Updated loyalty_programs {obj_id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating loyalty_programs {obj_id}: {str(e)}")
            raise

    async def delete(self, obj_id: int, user_id: Optional[str] = None) -> bool:
        """Delete loyalty_programs (requires ownership)"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            if not obj:
                logger.warning(f"Loyalty_programs {obj_id} not found for deletion")
                return False
            await self.db.delete(obj)
            await self.db.commit()
            logger.info(f"Deleted loyalty_programs {obj_id}")
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting loyalty_programs {obj_id}: {str(e)}")
            raise

    async def get_by_field(self, field_name: str, field_value: Any) -> Optional[Loyalty_programs]:
        """Get loyalty_programs by any field"""
        try:
            if not hasattr(Loyalty_programs, field_name):
                raise ValueError(f"Field {field_name} does not exist on Loyalty_programs")
            result = await self.db.execute(
                select(Loyalty_programs).where(getattr(Loyalty_programs, field_name) == field_value)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching loyalty_programs by {field_name}: {str(e)}")
            raise

    async def list_by_field(
        self, field_name: str, field_value: Any, skip: int = 0, limit: int = 20
    ) -> List[Loyalty_programs]:
        """Get list of loyalty_programss filtered by field"""
        try:
            if not hasattr(Loyalty_programs, field_name):
                raise ValueError(f"Field {field_name} does not exist on Loyalty_programs")
            result = await self.db.execute(
                select(Loyalty_programs)
                .where(getattr(Loyalty_programs, field_name) == field_value)
                .offset(skip)
                .limit(limit)
                .order_by(Loyalty_programs.id.desc())
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error fetching loyalty_programss by {field_name}: {str(e)}")
            raise