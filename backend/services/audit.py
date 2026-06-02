"""Audit-trail writer.

The ``audit_logs`` table existed as CRUD-only scaffolding that was never written
automatically on mutations. ``write_audit_log`` is a best-effort helper that
persists one row in its own session so a logging failure can never break (or roll
back) the request it is recording.
"""
import logging
from typing import Optional

from core.database import db_manager
from models.audit_logs import Audit_logs

logger = logging.getLogger(__name__)


async def write_audit_log(
    user_id: str,
    action: str,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Persist a single audit row. Never raises — failures are logged and swallowed."""
    if not db_manager.async_session_maker:
        return
    try:
        async with db_manager.async_session_maker() as db:
            db.add(
                Audit_logs(
                    user_id=str(user_id),
                    action=action,
                    details=(details or "")[:2000] or None,
                    ip_address=ip_address,
                )
            )
            await db.commit()
    except Exception as exc:  # pragma: no cover - defensive; auditing must not break requests
        logger.warning("Failed to write audit log (%s): %s", action, exc)
