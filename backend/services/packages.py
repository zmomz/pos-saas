import json
import logging
from typing import Optional, Dict, Any, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.features import FEATURE_KEYS
from models.packages import Packages

logger = logging.getLogger(__name__)


# ------------------ MA-07 feature-entitlement tier helpers ------------------
def normalize_feature_tier(value: Any) -> Optional[str]:
    """Validate + JSON-serialize a package feature tier for storage.

    ``value`` is the list of ENABLED feature keys the package unlocks, or ``None``
    for "no tier" (the package does not restrict features). Returns a canonical
    JSON string (deduped, sorted) or ``None``. Raises ``ValueError`` on a key
    outside ``FEATURE_KEYS`` so an invalid tier is rejected at the boundary rather
    than silently stored.
    """
    if value is None:
        return None
    if isinstance(value, str):  # already serialized (defensive)
        return value
    unknown = sorted({f for f in value if f not in FEATURE_KEYS})
    if unknown:
        raise ValueError(f"Unknown feature keys: {', '.join(unknown)}")
    chosen = set(value)
    return json.dumps([k for k in sorted(FEATURE_KEYS) if k in chosen])


def parse_feature_tier(raw: Any) -> Optional[List[str]]:
    """Parse a package's stored feature tier into a list of enabled keys, or None.

    ``None`` means the package defines no tier (do not restrict). A malformed
    stored value degrades to ``None`` rather than raising.
    """
    if not raw:
        return None
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, list) else None


# ------------------ Service Layer ------------------
class PackagesService:
    """Service layer for Packages operations"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: Dict[str, Any]) -> Optional[Packages]:
        """Create a new packages"""
        try:
            obj = Packages(**data)
            self.db.add(obj)
            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Created packages with id: {obj.id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating packages: {str(e)}")
            raise

    async def get_by_id(self, obj_id: int) -> Optional[Packages]:
        """Get packages by ID"""
        try:
            query = select(Packages).where(Packages.id == obj_id)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching packages {obj_id}: {str(e)}")
            raise

    async def get_list(
        self, 
        skip: int = 0, 
        limit: int = 20, 
        query_dict: Optional[Dict[str, Any]] = None,
        sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get paginated list of packagess"""
        try:
            query = select(Packages)
            count_query = select(func.count(Packages.id))
            
            if query_dict:
                for field, value in query_dict.items():
                    if hasattr(Packages, field):
                        query = query.where(getattr(Packages, field) == value)
                        count_query = count_query.where(getattr(Packages, field) == value)
            
            count_result = await self.db.execute(count_query)
            total = count_result.scalar()

            if sort:
                if sort.startswith('-'):
                    field_name = sort[1:]
                    if hasattr(Packages, field_name):
                        query = query.order_by(getattr(Packages, field_name).desc())
                else:
                    if hasattr(Packages, sort):
                        query = query.order_by(getattr(Packages, sort))
            else:
                query = query.order_by(Packages.id.desc())

            result = await self.db.execute(query.offset(skip).limit(limit))
            items = result.scalars().all()

            return {
                "items": items,
                "total": total,
                "skip": skip,
                "limit": limit,
            }
        except Exception as e:
            logger.error(f"Error fetching packages list: {str(e)}")
            raise

    async def update(self, obj_id: int, update_data: Dict[str, Any]) -> Optional[Packages]:
        """Update packages"""
        try:
            obj = await self.get_by_id(obj_id)
            if not obj:
                logger.warning(f"Packages {obj_id} not found for update")
                return None
            for key, value in update_data.items():
                if hasattr(obj, key):
                    setattr(obj, key, value)

            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Updated packages {obj_id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating packages {obj_id}: {str(e)}")
            raise

    async def delete(self, obj_id: int) -> bool:
        """Delete packages"""
        try:
            obj = await self.get_by_id(obj_id)
            if not obj:
                logger.warning(f"Packages {obj_id} not found for deletion")
                return False
            await self.db.delete(obj)
            await self.db.commit()
            logger.info(f"Deleted packages {obj_id}")
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting packages {obj_id}: {str(e)}")
            raise

    async def get_by_field(self, field_name: str, field_value: Any) -> Optional[Packages]:
        """Get packages by any field"""
        try:
            if not hasattr(Packages, field_name):
                raise ValueError(f"Field {field_name} does not exist on Packages")
            result = await self.db.execute(
                select(Packages).where(getattr(Packages, field_name) == field_value)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching packages by {field_name}: {str(e)}")
            raise

    async def list_by_field(
        self, field_name: str, field_value: Any, skip: int = 0, limit: int = 20
    ) -> List[Packages]:
        """Get list of packagess filtered by field"""
        try:
            if not hasattr(Packages, field_name):
                raise ValueError(f"Field {field_name} does not exist on Packages")
            result = await self.db.execute(
                select(Packages)
                .where(getattr(Packages, field_name) == field_value)
                .offset(skip)
                .limit(limit)
                .order_by(Packages.id.desc())
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error fetching packagess by {field_name}: {str(e)}")
            raise