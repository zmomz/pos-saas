import logging
from typing import Optional, Dict, Any, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.audit_logs import Audit_logs

logger = logging.getLogger(__name__)


def normalize_action(raw: Optional[str]) -> str:
    """Map a stored verbose audit action to a normalized verb the UI badges/filters on.

    The audit middleware records the raw ``METHOD /path`` of each mutation (e.g.
    ``POST /api/v1/entities/products``) and ``AUTH_FAILURE …`` for failed-auth
    attempts. The AuditLog page colours/filters by verb, so the read API maps the
    stored string to one of: ``create`` / ``update`` / ``delete`` / ``sale`` /
    ``export`` / ``auth_failure`` / ``other``. The stored compliance row is left
    untouched — this is a read-side projection only.
    """
    if not raw:
        return "other"
    text = raw.strip()
    if text.upper().startswith("AUTH_FAILURE"):
        return "auth_failure"
    parts = text.split()
    method = parts[0].upper() if parts else ""
    path = parts[1].lower() if len(parts) > 1 else ""
    if "export" in path:
        return "export"
    if method == "POST":
        # POS checkout records a sale rather than a generic create.
        if "/pos/transaction" in path or "/pos/sale" in path:
            return "sale"
        return "create"
    if method in ("PUT", "PATCH"):
        return "update"
    if method == "DELETE":
        return "delete"
    return "other"


# ------------------ Service Layer ------------------
class Audit_logsService:
    """Service layer for Audit_logs operations"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Audit_logs]:
        """Create a new audit_logs"""
        try:
            if user_id:
                data['user_id'] = user_id
            obj = Audit_logs(**data)
            self.db.add(obj)
            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Created audit_logs with id: {obj.id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating audit_logs: {str(e)}")
            raise

    async def check_ownership(self, obj_id: int, user_id: str) -> bool:
        """Check if user owns this record"""
        try:
            obj = await self.get_by_id(obj_id, owner_user_id=user_id)
            return obj is not None
        except Exception as e:
            logger.error(f"Error checking ownership for audit_logs {obj_id}: {str(e)}")
            return False

    async def get_by_id(self, obj_id: int, owner_user_id: Optional[str] = None) -> Optional[Audit_logs]:
        """Get audit_logs by ID, scoped to the owning merchant's tenant.

        ``owner_user_id`` is the tenancy owner (the merchant), not the actor, so a
        merchant sees rows produced by their staff. ``None`` (platform master) is
        unrestricted (finding H4).
        """
        try:
            query = select(Audit_logs).where(Audit_logs.id == obj_id)
            if owner_user_id:
                query = query.where(Audit_logs.owner_user_id == owner_user_id)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching audit_logs {obj_id}: {str(e)}")
            raise

    async def get_list(
        self,
        skip: int = 0,
        limit: int = 20,
        owner_user_id: Optional[str] = None,
        query_dict: Optional[Dict[str, Any]] = None,
        sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get paginated list of audit_logss, scoped to the owning merchant's tenant.

        Scopes on ``owner_user_id`` (the merchant), not the actor, so a merchant's
        audit query surfaces all their staff's actions. ``None`` (platform master)
        is unrestricted (finding H4).
        """
        try:
            query = select(Audit_logs)
            count_query = select(func.count(Audit_logs.id))

            if owner_user_id:
                query = query.where(Audit_logs.owner_user_id == owner_user_id)
                count_query = count_query.where(Audit_logs.owner_user_id == owner_user_id)
            
            if query_dict:
                for field, value in query_dict.items():
                    if hasattr(Audit_logs, field):
                        query = query.where(getattr(Audit_logs, field) == value)
                        count_query = count_query.where(getattr(Audit_logs, field) == value)
            
            count_result = await self.db.execute(count_query)
            total = count_result.scalar()

            if sort:
                if sort.startswith('-'):
                    field_name = sort[1:]
                    if hasattr(Audit_logs, field_name):
                        query = query.order_by(getattr(Audit_logs, field_name).desc())
                else:
                    if hasattr(Audit_logs, sort):
                        query = query.order_by(getattr(Audit_logs, sort))
            else:
                query = query.order_by(Audit_logs.id.desc())

            result = await self.db.execute(query.offset(skip).limit(limit))
            items = result.scalars().all()

            return {
                "items": items,
                "total": total,
                "skip": skip,
                "limit": limit,
            }
        except Exception as e:
            logger.error(f"Error fetching audit_logs list: {str(e)}")
            raise

    async def update(self, obj_id: int, update_data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Audit_logs]:
        """Update audit_logs (requires ownership)"""
        try:
            obj = await self.get_by_id(obj_id, owner_user_id=user_id)
            if not obj:
                logger.warning(f"Audit_logs {obj_id} not found for update")
                return None
            for key, value in update_data.items():
                if hasattr(obj, key) and key != 'user_id':
                    setattr(obj, key, value)

            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Updated audit_logs {obj_id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating audit_logs {obj_id}: {str(e)}")
            raise

    async def delete(self, obj_id: int, user_id: Optional[str] = None) -> bool:
        """Delete audit_logs (requires ownership)"""
        try:
            obj = await self.get_by_id(obj_id, owner_user_id=user_id)
            if not obj:
                logger.warning(f"Audit_logs {obj_id} not found for deletion")
                return False
            await self.db.delete(obj)
            await self.db.commit()
            logger.info(f"Deleted audit_logs {obj_id}")
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting audit_logs {obj_id}: {str(e)}")
            raise

    async def _email_map(self, user_ids: List[Optional[str]]) -> Dict[str, str]:
        """Resolve a set of actor ``user_id``s to their emails in one query."""
        from models.auth import User

        ids = {uid for uid in user_ids if uid}
        if not ids:
            return {}
        result = await self.db.execute(
            select(User.id, User.email).where(User.id.in_(ids))
        )
        return {row[0]: row[1] for row in result.all()}

    async def render_rows(self, rows: List[Audit_logs]) -> List[Dict[str, Any]]:
        """Project stored audit rows to the shape the AuditLog page renders.

        Resolves the actor's ``user_email`` (so the User column isn't a bare id)
        and normalizes ``action`` to a verb (so badges/filters work), leaving the
        underlying compliance rows untouched.
        """
        emails = await self._email_map([r.user_id for r in rows])
        return [
            {
                "id": r.id,
                "user_id": r.user_id,
                "user_email": emails.get(r.user_id),
                "owner_user_id": r.owner_user_id,
                "action": normalize_action(r.action),
                "details": r.details,
                "ip_address": r.ip_address,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in rows
        ]

    async def get_by_field(self, field_name: str, field_value: Any) -> Optional[Audit_logs]:
        """Get audit_logs by any field"""
        try:
            if not hasattr(Audit_logs, field_name):
                raise ValueError(f"Field {field_name} does not exist on Audit_logs")
            result = await self.db.execute(
                select(Audit_logs).where(getattr(Audit_logs, field_name) == field_value)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching audit_logs by {field_name}: {str(e)}")
            raise

    async def list_by_field(
        self, field_name: str, field_value: Any, skip: int = 0, limit: int = 20
    ) -> List[Audit_logs]:
        """Get list of audit_logss filtered by field"""
        try:
            if not hasattr(Audit_logs, field_name):
                raise ValueError(f"Field {field_name} does not exist on Audit_logs")
            result = await self.db.execute(
                select(Audit_logs)
                .where(getattr(Audit_logs, field_name) == field_value)
                .offset(skip)
                .limit(limit)
                .order_by(Audit_logs.id.desc())
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error fetching audit_logss by {field_name}: {str(e)}")
            raise