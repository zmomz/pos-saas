"""Customer consent-event service (#227, SEC-05 / PDPL).

Append an immutable consent-change row to a customer's trail and read the trail
back newest-first. Every operation is owner-scoped by ``user_id`` (SEC-02); the
caller (the router) confirms the customer belongs to that owner — via a 404 —
before recording or reading, so an event can never attach to a foreign customer.
"""
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.customer_consent_events import CustomerConsentEvent

logger = logging.getLogger(__name__)


class CustomerConsentService:
    """Service layer for a customer's append-only consent trail (#227)."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def record(
        self,
        customer_id: int,
        *,
        granted: bool,
        source: str,
        user_id: str,
        client_id: Optional[int] = None,
        actor: Optional[str] = None,
        consent_type: str = "marketing",
    ) -> CustomerConsentEvent:
        """Append one consent-change row (owner-scoped, SEC-02).

        Does NOT commit — the caller commits alongside the customer mutation the
        event evidences, so the snapshot and its trail move as one transaction."""
        event = CustomerConsentEvent(
            user_id=str(user_id),
            client_id=client_id,
            customer_id=customer_id,
            consent_type=consent_type,
            granted=bool(granted),
            source=source,
            actor=(actor or None),
        )
        self.db.add(event)
        return event

    async def list(self, customer_id: int, *, user_id: str) -> list[CustomerConsentEvent]:
        """The customer's consent events, newest-first (owner-scoped, SEC-02)."""
        rows = (
            await self.db.execute(
                select(CustomerConsentEvent)
                .where(
                    CustomerConsentEvent.customer_id == customer_id,
                    CustomerConsentEvent.user_id == str(user_id),
                )
                .order_by(CustomerConsentEvent.id.desc())
            )
        ).scalars().all()
        return list(rows)
