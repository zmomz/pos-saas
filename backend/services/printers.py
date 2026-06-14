"""Saved-printer registry + per-station routing resolution (ISSUE-047, H26/U5.2).

A merchant registers printers (``Printers`` rows) and flags one per role as the
default. ``resolve_printer`` is the routing brain: given a printable's role
(``receipt``/``kot``) and an optional prep station, it picks the printer the
printout should stream to — a station-bound KOT printer first, then the role
default, mirroring how ``receipt_templates.load_default_template`` resolves the
merchant's default template.
"""
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.printers import Printers

logger = logging.getLogger(__name__)

ROLES = ("receipt", "kot")


class PrintersService:
    """Owner-scoped CRUD for the printer registry (SEC-02)."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _clear_other_defaults(self, user_id: str, role: str, keep_id: Optional[int]) -> None:
        """Only one printer per (owner, role) may carry ``is_default`` (single
        selected default), so flipping one on clears the rest."""
        stmt = (
            update(Printers)
            .where(
                Printers.user_id == user_id,
                Printers.role == role,
                Printers.is_default.is_(True),
            )
            .values(is_default=False)
        )
        if keep_id is not None:
            stmt = stmt.where(Printers.id != keep_id)
        await self.db.execute(stmt)

    async def create(self, data: Dict[str, Any], user_id: str) -> Printers:
        data = {**data, "user_id": user_id}
        obj = Printers(**data)
        self.db.add(obj)
        await self.db.flush()
        if obj.is_default:
            await self._clear_other_defaults(user_id, obj.role, keep_id=obj.id)
        await self.db.commit()
        await self.db.refresh(obj)
        return obj

    async def get_by_id(self, obj_id: int, user_id: str) -> Optional[Printers]:
        result = await self.db.execute(
            select(Printers).where(Printers.id == obj_id, Printers.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list(self, user_id: str) -> List[Printers]:
        result = await self.db.execute(
            select(Printers).where(Printers.user_id == user_id).order_by(Printers.id.desc())
        )
        return list(result.scalars().all())

    async def update(self, obj_id: int, data: Dict[str, Any], user_id: str) -> Optional[Printers]:
        obj = await self.get_by_id(obj_id, user_id)
        if obj is None:
            return None
        for key, value in data.items():
            if key not in ("id", "user_id") and hasattr(obj, key):
                setattr(obj, key, value)
        if obj.is_default:
            await self._clear_other_defaults(user_id, obj.role, keep_id=obj.id)
        await self.db.commit()
        await self.db.refresh(obj)
        return obj

    async def delete(self, obj_id: int, user_id: str) -> bool:
        obj = await self.get_by_id(obj_id, user_id)
        if obj is None:
            return False
        await self.db.delete(obj)
        await self.db.commit()
        return True


async def resolve_printer(
    db: AsyncSession,
    user_id: Optional[str],
    role: str,
    station_id: Optional[int] = None,
) -> Optional[Printers]:
    """Pick the active printer a ``role`` printable should route to.

    Resolution order (owner-scoped, active printers of the role only):

    1. **Station match** — when ``station_id`` is given (a KOT for a prep
       station), a printer bound to exactly that station wins, preferring one
       flagged default among them.
    2. **Role default** — otherwise the printer flagged ``is_default`` for the
       role, preferring a general one (no station binding) over a station-bound
       default.
    3. **Most-recent** — failing any default, the newest printer of the role.

    Returns ``None`` when the merchant has registered no usable printer (the
    caller then falls back to its built-in default print path). Best-effort: any
    error resolves to ``None`` so a routing lookup can never break the print path.
    """
    if not user_id or role not in ROLES:
        return None
    try:
        result = await db.execute(
            select(Printers).where(
                Printers.user_id == user_id,
                Printers.role == role,
                Printers.status == "active",
            ).order_by(Printers.id.desc())
        )
        rows = list(result.scalars().all())
        if not rows:
            return None

        if station_id is not None:
            station_matches = [p for p in rows if p.station_id == station_id]
            if station_matches:
                return _prefer_default(station_matches)

        defaults = [p for p in rows if p.is_default]
        if defaults:
            general = [p for p in defaults if p.station_id is None]
            return general[0] if general else defaults[0]

        return rows[0]
    except Exception:
        logger.warning("Failed to resolve printer; using built-in default path", exc_info=True)
        return None


def _prefer_default(printers: List[Printers]) -> Printers:
    for p in printers:
        if p.is_default:
            return p
    return printers[0]


def printer_echo(printer: Optional[Printers]) -> Optional[Dict[str, Any]]:
    """The resolved-device summary a print response echoes back so the browser
    streams to that printer instead of re-prompting (``None`` when nothing was
    resolved — the caller's built-in default path then takes over)."""
    if printer is None:
        return None
    return {
        "id": printer.id,
        "name": printer.name,
        "device_id": printer.device_id,
        "paper_size": printer.paper_size,
    }
