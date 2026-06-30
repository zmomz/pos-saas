"""Birthday-rewards service (CRM, #221).

A merchant runs a birthday-reward batch for a given day: every one of *their* own
customers whose ``date_of_birth`` falls on that month/day is granted a fixed amount
of store credit (a goodwill loyalty payout), booked onto the store-credit ledger as
a ``grant`` so it accrues and is auditable like any other movement.

The server is authoritative and owner-scoped (SEC-02): the run only ever resolves
customers under the caller's ``user_id``. It is idempotent per birthday *year* — the
grant carries a year-stamped marker note and a customer already rewarded for that
year is skipped, so re-running the same day never double-grants (REV-03). Customers
who are blacklisted (not in good standing) or PII-erased (no usable identity) are
skipped.
"""
import logging
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.money import quantize_money
from models.customers import Customers
from models.store_credit_ledger import StoreCreditLedger
from services.store_credit import GRANT, StoreCreditError, StoreCreditService

logger = logging.getLogger(__name__)


def _marker(on_date: date) -> str:
    """The year-stamped ledger note that makes a birthday grant idempotent."""
    return f"Birthday reward {on_date.year}"


class BirthdayRewardsService:
    """Service layer for the birthday-reward batch (#221)."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _eligible(self, *, user_id: str, on_date: date) -> list[Customers]:
        """The owner's customers whose birthday falls on ``on_date`` (month/day).

        Owner-scoped (SEC-02). The month/day match is done in Python (over only the
        owner's rows that carry a DOB) so it stays portable across SQLite/Postgres.
        Blacklisted and PII-erased customers are excluded — they are not rewardable.
        """
        rows = (
            await self.db.execute(
                select(Customers).where(
                    Customers.user_id == str(user_id),
                    Customers.date_of_birth.is_not(None),
                    Customers.blacklisted_at.is_(None),
                    Customers.pii_erased_at.is_(None),
                )
            )
        ).scalars().all()
        return [
            c
            for c in rows
            if c.date_of_birth.month == on_date.month
            and c.date_of_birth.day == on_date.day
        ]

    async def _already_rewarded(self, customer_id: int, *, user_id: str, marker: str) -> bool:
        """True when this customer already has a birthday grant for this year."""
        existing = (
            await self.db.execute(
                select(StoreCreditLedger.id).where(
                    StoreCreditLedger.customer_id == customer_id,
                    StoreCreditLedger.user_id == str(user_id),
                    StoreCreditLedger.entry_type == GRANT,
                    StoreCreditLedger.note == marker,
                )
            )
        ).first()
        return existing is not None

    async def run(
        self,
        *,
        user_id: str,
        client_id: Optional[int],
        on_date: date,
        amount: float,
    ) -> list[dict]:
        """Grant ``amount`` of store credit to every customer whose birthday is today.

        Returns one ``{customer_id, name, balance}`` row per customer actually
        rewarded this run (those already rewarded for this birthday year are
        skipped). Raises :class:`StoreCreditError` if ``amount`` is not positive.
        """
        if quantize_money(amount or 0) <= 0:
            raise StoreCreditError("Birthday reward amount must be positive.")
        marker = _marker(on_date)
        credit = StoreCreditService(self.db)
        rewarded: list[dict] = []
        for customer in await self._eligible(user_id=user_id, on_date=on_date):
            if await self._already_rewarded(customer.id, user_id=user_id, marker=marker):
                continue
            row = await credit.post(
                customer.id,
                user_id=user_id,
                client_id=client_id,
                entry_type=GRANT,
                amount=amount,
                note=marker,
            )
            rewarded.append(
                {
                    "customer_id": customer.id,
                    "name": customer.name,
                    "balance": float(row.balance_after),
                }
            )
        logger.info(
            "Birthday rewards: granted %s to %d customer(s) for %s",
            amount,
            len(rewarded),
            on_date.isoformat(),
        )
        return rewarded
