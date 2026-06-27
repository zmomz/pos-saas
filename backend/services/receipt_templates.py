import logging
from typing import Optional, Dict, Any, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.receipt_templates import Receipt_templates
from services.query_filter import apply_query_filters

# SEC-17: columns a client may filter on via the list endpoint's ?query=.
FILTERABLE_FIELDS = frozenset({"client_id", "id", "is_default", "name"})

logger = logging.getLogger(__name__)


# ------------------ Service Layer ------------------
class Receipt_templatesService:
    """Service layer for Receipt_templates operations"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Receipt_templates]:
        """Create a new receipt_templates"""
        try:
            if user_id:
                data['user_id'] = user_id
            obj = Receipt_templates(**data)
            self.db.add(obj)
            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Created receipt_templates with id: {obj.id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating receipt_templates: {str(e)}")
            raise

    async def check_ownership(self, obj_id: int, user_id: str) -> bool:
        """Check if user owns this record"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            return obj is not None
        except Exception as e:
            logger.error(f"Error checking ownership for receipt_templates {obj_id}: {str(e)}")
            return False

    async def get_by_id(self, obj_id: int, user_id: Optional[str] = None) -> Optional[Receipt_templates]:
        """Get receipt_templates by ID (user can only see their own records)"""
        try:
            query = select(Receipt_templates).where(Receipt_templates.id == obj_id)
            if user_id:
                query = query.where(Receipt_templates.user_id == user_id)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching receipt_templates {obj_id}: {str(e)}")
            raise

    async def get_list(
        self, 
        skip: int = 0, 
        limit: int = 20, 
        user_id: Optional[str] = None,
        query_dict: Optional[Dict[str, Any]] = None,
        sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get paginated list of receipt_templatess (user can only see their own records)"""
        try:
            query = select(Receipt_templates)
            count_query = select(func.count(Receipt_templates.id))
            
            if user_id:
                query = query.where(Receipt_templates.user_id == user_id)
                count_query = count_query.where(Receipt_templates.user_id == user_id)
            
            query, count_query = apply_query_filters(
                Receipt_templates, query, count_query, query_dict, FILTERABLE_FIELDS
            )
            
            count_result = await self.db.execute(count_query)
            total = count_result.scalar()

            if sort:
                if sort.startswith('-'):
                    field_name = sort[1:]
                    if hasattr(Receipt_templates, field_name):
                        query = query.order_by(getattr(Receipt_templates, field_name).desc())
                else:
                    if hasattr(Receipt_templates, sort):
                        query = query.order_by(getattr(Receipt_templates, sort))
            else:
                query = query.order_by(Receipt_templates.id.desc())

            result = await self.db.execute(query.offset(skip).limit(limit))
            items = result.scalars().all()

            return {
                "items": items,
                "total": total,
                "skip": skip,
                "limit": limit,
            }
        except Exception as e:
            logger.error(f"Error fetching receipt_templates list: {str(e)}")
            raise

    async def update(self, obj_id: int, update_data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Receipt_templates]:
        """Update receipt_templates (requires ownership)"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            if not obj:
                logger.warning(f"Receipt_templates {obj_id} not found for update")
                return None
            for key, value in update_data.items():
                if hasattr(obj, key) and key != 'user_id':
                    setattr(obj, key, value)

            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Updated receipt_templates {obj_id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating receipt_templates {obj_id}: {str(e)}")
            raise

    async def delete(self, obj_id: int, user_id: Optional[str] = None) -> bool:
        """Delete receipt_templates (requires ownership)"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            if not obj:
                logger.warning(f"Receipt_templates {obj_id} not found for deletion")
                return False
            await self.db.delete(obj)
            await self.db.commit()
            logger.info(f"Deleted receipt_templates {obj_id}")
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting receipt_templates {obj_id}: {str(e)}")
            raise

    async def get_by_field(self, field_name: str, field_value: Any) -> Optional[Receipt_templates]:
        """Get receipt_templates by any field"""
        try:
            if not hasattr(Receipt_templates, field_name):
                raise ValueError(f"Field {field_name} does not exist on Receipt_templates")
            result = await self.db.execute(
                select(Receipt_templates).where(getattr(Receipt_templates, field_name) == field_value)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching receipt_templates by {field_name}: {str(e)}")
            raise

    async def list_by_field(
        self, field_name: str, field_value: Any, skip: int = 0, limit: int = 20
    ) -> List[Receipt_templates]:
        """Get list of receipt_templatess filtered by field"""
        try:
            if not hasattr(Receipt_templates, field_name):
                raise ValueError(f"Field {field_name} does not exist on Receipt_templates")
            result = await self.db.execute(
                select(Receipt_templates)
                .where(getattr(Receipt_templates, field_name) == field_value)
                .offset(skip)
                .limit(limit)
                .order_by(Receipt_templates.id.desc())
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error fetching receipt_templatess by {field_name}: {str(e)}")
            raise


# H26 (ISSUE-045): the render knobs the ESC/POS builders honor. Mirrors the
# template fields `escpos.build_receipt`/`build_kot` read out of the dict.
_TEMPLATE_KNOBS = ("header_text", "footer_text", "show_logo", "show_qr_code", "show_vat_details", "paper_size", "font_size")


async def load_default_template(db: AsyncSession, user_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Return the merchant's default receipt template as a plain render-knob dict.

    Picks the template flagged ``is_default`` for the owner; failing that, the
    most-recent template; ``None`` when the merchant has none (the renderer then
    uses its built-in defaults). Returns a plain dict — not the ORM row — so the
    pure, DB-free ``escpos`` renderer stays decoupled from the database.

    Best-effort: any error resolves to ``None`` so a template lookup can never
    break the print/receipt path (OPS-08).
    """
    if not user_id:
        return None
    try:
        service = Receipt_templatesService(db)
        result = await service.get_list(
            limit=1, user_id=user_id, query_dict={"is_default": True}
        )
        items = result.get("items") or []
        if not items:
            result = await service.get_list(limit=1, user_id=user_id)
            items = result.get("items") or []
        if not items:
            return None
        row = items[0]
        return {knob: getattr(row, knob, None) for knob in _TEMPLATE_KNOBS}
    except Exception:
        logger.warning("Failed to load default receipt template; using renderer defaults", exc_info=True)
        return None