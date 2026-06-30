"""Supplier-credit service (M4 Inventory, #224).

The vendor-facing balance that accrues when a merchant returns received goods to a
supplier: a **supplier credit note**. Every movement is appended to
``supplier_credit_ledger`` with the resulting ``balance_after``, mirroring the
store-credit ledger so the balance is auditable rather than a single mutable number.

The server is authoritative (SEC-02 / REV-03): a draw-down is validated against the
*current* balance in the same call that books it, so a supplier's credit can never be
overdrawn, and the amount is decimal-quantized so the balance never drifts. The
caller scopes by ``user_id`` (the tenancy owner); callers must confirm the supplier
belongs to that owner before posting (the router does, via 404).
"""
import logging
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.money import quantize_money
from models.supplier_credit_ledger import SupplierCreditLedger

logger = logging.getLogger(__name__)

CREDIT_NOTE = "credit_note"
APPLIED = "applied"
ADJUST = "adjust"

# Movements that add to the balance vs. subtract from it.
_CREDIT_TYPES = {CREDIT_NOTE, ADJUST}
_DEBIT_TYPES = {APPLIED}


class SupplierCreditError(ValueError):
    """A supplier-credit movement failed server-side validation (mapped to HTTP 400).

    Raised for a non-positive amount, an unknown entry type, or a draw-down that
    would overdraw the supplier's outstanding credit.
    """


class SupplierCreditService:
    """Service layer for a supplier's outstanding credit balance and ledger."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def balance(self, supplier_id: int, *, user_id: str) -> Decimal:
        """The supplier's current outstanding credit balance (owner-scoped, SEC-02).

        Computed as the sum of every signed movement in SQL (never load-everything,
        OPS-05). Zero when the supplier has no ledger rows."""
        total = (
            await self.db.execute(
                select(func.coalesce(func.sum(SupplierCreditLedger.amount), 0)).where(
                    SupplierCreditLedger.supplier_id == supplier_id,
                    SupplierCreditLedger.user_id == str(user_id),
                )
            )
        ).scalar()
        return quantize_money(total or 0)

    async def history(self, supplier_id: int, *, user_id: str) -> list[SupplierCreditLedger]:
        """The supplier's movements oldest-first (owner-scoped, SEC-02)."""
        rows = (
            await self.db.execute(
                select(SupplierCreditLedger)
                .where(
                    SupplierCreditLedger.supplier_id == supplier_id,
                    SupplierCreditLedger.user_id == str(user_id),
                )
                .order_by(SupplierCreditLedger.id)
            )
        ).scalars().all()
        return list(rows)

    async def post(
        self,
        supplier_id: int,
        *,
        user_id: str,
        client_id: Optional[int],
        entry_type: str,
        amount: float,
        note: Optional[str] = None,
        purchase_order_id: Optional[int] = None,
    ) -> SupplierCreditLedger:
        """Book one movement and persist it, returning the new ledger row.

        ``amount`` is always supplied as a positive magnitude; the sign is derived
        from ``entry_type`` (credit vs. debit). A draw-down is checked against the
        live balance so it can never overdraw."""
        kind = (entry_type or "").strip().lower()
        if kind not in _CREDIT_TYPES and kind not in _DEBIT_TYPES:
            raise SupplierCreditError(f"Unknown supplier-credit entry type: {entry_type!r}")

        magnitude = quantize_money(amount or 0)
        if magnitude <= 0:
            raise SupplierCreditError("Supplier-credit amount must be positive.")

        current = await self.balance(supplier_id, user_id=user_id)
        if kind in _DEBIT_TYPES:
            if magnitude > current:
                raise SupplierCreditError(
                    f"Insufficient supplier credit: balance {current} < requested {magnitude}."
                )
            signed = -magnitude
        else:
            signed = magnitude

        new_balance = quantize_money(current + signed)
        row = SupplierCreditLedger(
            user_id=str(user_id),
            client_id=client_id,
            supplier_id=supplier_id,
            entry_type=kind,
            amount=signed,
            balance_after=new_balance,
            purchase_order_id=purchase_order_id,
            note=note,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        logger.info(
            "Supplier-credit %s %.2f for supplier %s (balance %.2f)",
            kind,
            float(signed),
            supplier_id,
            float(new_balance),
        )
        return row
