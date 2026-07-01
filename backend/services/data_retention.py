"""Data-retention policy service — PDPL data-minimization (#227, SEC-05).

Reads/writes a tenant's dormant-PII retention window and *enforces* it: every
customer whose PII is still present and whose ``updated_at`` is older than the
window is minimized via the same PDPL erasure the ``/erase`` endpoint applies —
name tombstoned, phone/email/VAT/notes nulled, marketing consent withdrawn,
``pii_erased_at`` stamped. Erasure (not deletion) keeps the fiscal row intact so
ZATCA's 6-year invoice-retention obligation still holds.

Every operation is owner-scoped by ``user_id`` (SEC-02): a tenant's policy and
enforcement can never reach another tenant's customers. The service mutates but
does NOT commit — the caller (the router) commits, so the policy read/write and
the erasures it drives settle as one transaction (mirrors the consent service).
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.audit_logs import Audit_logs
from models.customers import Customers
from models.data_retention_policy import DataRetentionPolicy
from services.customer_consent import CustomerConsentService

logger = logging.getLogger(__name__)


class DataRetentionService:
    """Service layer for a tenant's PDPL data-retention policy (#227)."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_policy(self, *, user_id: str) -> Optional[DataRetentionPolicy]:
        """The tenant's policy row, or None when never configured (SEC-02)."""
        return (
            await self.db.execute(
                select(DataRetentionPolicy).where(
                    DataRetentionPolicy.user_id == str(user_id)
                )
            )
        ).scalar_one_or_none()

    async def set_policy(
        self,
        *,
        user_id: str,
        customer_pii_retention_days: Optional[int],
        client_id: Optional[int] = None,
    ) -> DataRetentionPolicy:
        """Upsert the tenant's retention window (owner-scoped, SEC-02).

        ``customer_pii_retention_days`` is a positive day count, or None to disable
        retention. Does NOT commit — the caller commits."""
        policy = await self.get_policy(user_id=user_id)
        if policy is None:
            policy = DataRetentionPolicy(
                user_id=str(user_id), client_id=client_id
            )
            self.db.add(policy)
        policy.customer_pii_retention_days = customer_pii_retention_days
        # A stamp so the client can surface "policy last changed" and so onupdate
        # fires even on a first insert.
        policy.updated_at = datetime.now()
        return policy

    async def enforce(
        self, *, user_id: str, client_id: Optional[int], actor: Optional[str]
    ) -> list[int]:
        """Minimize dormant customer PII per the tenant's policy (owner-scoped).

        Returns the ids of customers erased this run. A no-op (empty list) when no
        policy is set, retention is disabled, or nothing is past the window. Does
        NOT commit — the caller commits the whole batch as one transaction."""
        policy = await self.get_policy(user_id=user_id)
        if policy is None or not policy.customer_pii_retention_days:
            return []

        now = datetime.now()
        cutoff = now - timedelta(days=int(policy.customer_pii_retention_days))
        due = (
            await self.db.execute(
                select(Customers).where(
                    Customers.user_id == str(user_id),
                    # Already-tombstoned rows carry pii_erased_at — never re-erase.
                    Customers.pii_erased_at.is_(None),
                    Customers.updated_at < cutoff,
                )
            )
        ).scalars().all()

        consent = CustomerConsentService(self.db)
        erased: list[int] = []
        for customer in due:
            consent_withdrawn = bool(customer.marketing_consent)
            # ``name`` is NOT NULL — tombstone rather than null (mirrors /erase).
            customer.name = "[erased]"
            customer.phone = None
            customer.email = None
            customer.vat_number = None
            customer.notes = None
            customer.marketing_consent = False
            customer.consent_updated_at = now
            customer.pii_erased_at = now

            if consent_withdrawn:
                await consent.record(
                    customer.id,
                    granted=False,
                    source="erase",
                    user_id=str(user_id),
                    client_id=client_id,
                    actor=actor,
                )

            self.db.add(
                Audit_logs(
                    user_id=str(actor) if actor is not None else str(user_id),
                    action="PDPL_RETENTION_ERASE_CUSTOMER",
                    entity_type="customers",
                    entity_id=str(customer.id),
                    details=(
                        f"Erased PII for customer {customer.id} under the "
                        f"{policy.customer_pii_retention_days}-day retention policy "
                        "(PDPL data-minimization)"
                    ),
                )
            )
            erased.append(customer.id)

        if erased:
            logger.info(
                "Retention policy erased PII for %d dormant customer(s) (tenant %s)",
                len(erased),
                user_id,
            )
        return erased
