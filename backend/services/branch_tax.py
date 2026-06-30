"""Per-branch VAT rate overrides (#220 multi-branch: branch-level tax).

The chain-wide effective rate is the master's global VAT rate (MA-05) when set,
else the statutory KSA default (``DEFAULT_TAX_RATE``). A branch may override it
for itself; absent an override the chain rate applies. Every read/write is scoped
to the caller's ``client_id`` (SEC-02), so one tenant's branch tax rates never
leak into another's.

``resolve_tax_rate`` is wired into checkout (``POST /pos/transaction``): a sale
rung up at a branch is taxed at the branch's resolved rate (#220 sale-time
enforcement). Branch-level *price* enforcement remains the next "then expand".
"""
import logging
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.branch_tax_rate import Branch_tax_rate
from services.system_settings import get_effective_tax_rate

logger = logging.getLogger(__name__)


async def _get_row(
    db: AsyncSession, client_id: int, branch_id: int
) -> Optional[Branch_tax_rate]:
    return (
        await db.execute(
            select(Branch_tax_rate).where(
                Branch_tax_rate.client_id == client_id,
                Branch_tax_rate.branch_id == branch_id,
            )
        )
    ).scalar_one_or_none()


async def set_branch_tax_rate(
    db: AsyncSession, user_id: str, client_id: int, branch_id: int, vat_rate: float
) -> Branch_tax_rate:
    """Upsert a branch VAT-rate override (commits).

    One row per (client_id, branch_id): a second set updates the existing row's
    rate rather than inserting a duplicate. The rate is clamped to ``[0, 100]``.
    """
    rate = min(100.0, max(0.0, float(vat_rate)))
    row = await _get_row(db, client_id, branch_id)
    if row is None:
        row = Branch_tax_rate(
            user_id=str(user_id),
            client_id=client_id,
            branch_id=branch_id,
            vat_rate=rate,
        )
        db.add(row)
    else:
        await db.execute(
            update(Branch_tax_rate)
            .where(Branch_tax_rate.id == row.id)
            .values(vat_rate=rate)
        )
    await db.commit()
    await db.refresh(row)
    return row


async def delete_branch_tax_rate(
    db: AsyncSession, client_id: int, branch_id: int
) -> bool:
    """Remove a branch override so it falls back to the chain effective rate."""
    row = await _get_row(db, client_id, branch_id)
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def resolve_tax_rate(
    db: AsyncSession, client_id: int, branch_id: int, requested: Optional[float] = None
) -> dict:
    """Resolve the effective VAT rate for a branch.

    Returns ``{"branch_id", "vat_rate", "is_override"}``: the branch override rate
    when one exists, else the chain-wide effective rate. ``requested`` is the
    legacy per-request rate; it only matters in the no-override fallback, where it
    is threaded into ``get_effective_tax_rate`` so the master global rate (MA-05)
    still wins but a request rate is honoured on installs with no global rate.
    """
    row = await _get_row(db, client_id, branch_id)
    if row is not None:
        return {
            "branch_id": branch_id,
            "vat_rate": row.vat_rate,
            "is_override": True,
        }
    chain_rate = await get_effective_tax_rate(db, requested)
    return {
        "branch_id": branch_id,
        "vat_rate": chain_rate,
        "is_override": False,
    }
