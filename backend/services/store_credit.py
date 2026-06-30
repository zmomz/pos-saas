"""Store-credit service (CRM, #221).

The merchant-facing balance that lives on a ``customers`` row: grant credit, spend
it, and read its running balance + history. Every movement is appended to
``store_credit_ledger`` with the resulting ``balance_after``, mirroring the gift-card
ledger so the balance is auditable rather than a single mutable number.

The server is authoritative (SEC-02 / REV-03): a redemption is validated against the
*current* balance in the same call that books it, so a customer's credit can never be
overdrawn, and the amount is decimal-quantized so the balance never drifts. The
caller scopes by ``user_id`` (the tenancy owner); callers must confirm the customer
belongs to that owner before granting/redeeming (the router does, via 404).
"""
import logging
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.money import quantize_money
from models.store_credit_ledger import StoreCreditLedger

logger = logging.getLogger(__name__)

GRANT = "grant"
REDEEM = "redeem"
ADJUST = "adjust"
REFUND = "refund"

# Movements that add to the balance vs. subtract from it.
_CREDIT_TYPES = {GRANT, REFUND}
_DEBIT_TYPES = {REDEEM}


class StoreCreditError(ValueError):
    """A store-credit movement failed server-side validation (mapped to HTTP 400).

    Raised for a non-positive amount, an unknown entry type, or a redemption that
    would overdraw the customer's balance.
    """


class StoreCreditService:
    """Service layer for a customer's store-credit balance and ledger."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def balance(self, customer_id: int, *, user_id: str) -> Decimal:
        """The customer's current store-credit balance (owner-scoped, SEC-02).

        Computed as the sum of every signed movement in SQL (never load-everything,
        OPS-05). Zero when the customer has no ledger rows."""
        total = (
            await self.db.execute(
                select(func.coalesce(func.sum(StoreCreditLedger.amount), 0)).where(
                    StoreCreditLedger.customer_id == customer_id,
                    StoreCreditLedger.user_id == str(user_id),
                )
            )
        ).scalar()
        return quantize_money(total or 0)

    async def history(self, customer_id: int, *, user_id: str) -> list[StoreCreditLedger]:
        """The customer's movements oldest-first (owner-scoped, SEC-02)."""
        rows = (
            await self.db.execute(
                select(StoreCreditLedger)
                .where(
                    StoreCreditLedger.customer_id == customer_id,
                    StoreCreditLedger.user_id == str(user_id),
                )
                .order_by(StoreCreditLedger.id)
            )
        ).scalars().all()
        return list(rows)

    async def post(
        self,
        customer_id: int,
        *,
        user_id: str,
        client_id: Optional[int],
        entry_type: str,
        amount: float,
        note: Optional[str] = None,
        transaction_id: Optional[int] = None,
    ) -> StoreCreditLedger:
        """Book one movement and persist it, returning the new ledger row.

        ``amount`` is always supplied as a positive magnitude; the sign is derived
        from ``entry_type`` (credit vs. debit). A redemption is checked against the
        live balance so it can never overdraw."""
        kind = (entry_type or "").strip().lower()
        if kind not in _CREDIT_TYPES and kind not in _DEBIT_TYPES:
            raise StoreCreditError(f"Unknown store-credit entry type: {entry_type!r}")

        magnitude = quantize_money(amount or 0)
        if magnitude <= 0:
            raise StoreCreditError("Store-credit amount must be positive.")

        current = await self.balance(customer_id, user_id=user_id)
        if kind in _DEBIT_TYPES:
            if magnitude > current:
                raise StoreCreditError(
                    f"Insufficient store credit: balance {current} < requested {magnitude}."
                )
            signed = -magnitude
        else:
            signed = magnitude

        new_balance = quantize_money(current + signed)
        row = StoreCreditLedger(
            user_id=str(user_id),
            client_id=client_id,
            customer_id=customer_id,
            entry_type=kind,
            amount=signed,
            balance_after=new_balance,
            transaction_id=transaction_id,
            note=note,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        logger.info(
            "Store-credit %s %.2f for customer %s (balance %.2f)",
            kind,
            float(signed),
            customer_id,
            float(new_balance),
        )
        return row
