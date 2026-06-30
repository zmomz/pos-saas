"""Customer notes-thread service (CRM, #221).

Append a note to a customer's running log and read the thread newest-first. Every
operation is owner-scoped by ``user_id`` (SEC-02); the caller (the router) confirms
the customer belongs to that owner — via a 404 — before appending, so a note can
never be attached to a foreign customer.
"""
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.customer_notes import CustomerNote

logger = logging.getLogger(__name__)


class CustomerNoteError(ValueError):
    """A note failed server-side validation (mapped to HTTP 400) — e.g. blank body."""


class CustomerNotesService:
    """Service layer for a customer's append-only notes thread (#221)."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def add(
        self,
        customer_id: int,
        *,
        user_id: str,
        client_id: Optional[int],
        body: str,
        author: Optional[str] = None,
    ) -> CustomerNote:
        """Append a note to the customer's thread (owner-scoped, SEC-02).

        Raises ``CustomerNoteError`` when the body is blank — an empty note carries
        no signal."""
        text = (body or "").strip()
        if not text:
            raise CustomerNoteError("Note body must not be blank")
        note = CustomerNote(
            user_id=str(user_id),
            client_id=client_id,
            customer_id=customer_id,
            body=text,
            author=(author or "").strip() or None,
        )
        self.db.add(note)
        await self.db.commit()
        await self.db.refresh(note)
        logger.info("Added note %s to customer %s for %s", note.id, customer_id, user_id)
        return note

    async def list(self, customer_id: int, *, user_id: str) -> list[CustomerNote]:
        """The customer's notes, newest-first (owner-scoped, SEC-02)."""
        rows = (
            await self.db.execute(
                select(CustomerNote)
                .where(
                    CustomerNote.customer_id == customer_id,
                    CustomerNote.user_id == str(user_id),
                )
                .order_by(CustomerNote.id.desc())
            )
        ).scalars().all()
        return list(rows)
