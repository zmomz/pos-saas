"""Per-branch promotion opt-outs (#220 multi-branch: branch-level promotions).

A chain's auto-applied promotions (ISSUE-058) run at every branch by default. A
branch may opt out of a specific promotion; absent an opt-out the promotion runs.
Resolving a branch's effective promotion set returns all active chain promotions
minus the ones that branch has disabled. Every read/write is scoped to the
caller's ``client_id`` (SEC-02), so one tenant's branch overrides never leak into
another's.

Sale-time enforcement (pricing a branch sale against its resolved set) is the
"then expand" follow-up; this service resolves the effective set only, mirroring
``branch_pricing`` / ``branch_tax``.
"""
import logging
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.branch_promotion_override import Branch_promotion_override
from services.promotions import load_active_promotions

logger = logging.getLogger(__name__)


async def _get_row(
    db: AsyncSession, client_id: int, branch_id: int, promotion_id: int
) -> Optional[Branch_promotion_override]:
    return (
        await db.execute(
            select(Branch_promotion_override).where(
                Branch_promotion_override.client_id == client_id,
                Branch_promotion_override.branch_id == branch_id,
                Branch_promotion_override.promotion_id == promotion_id,
            )
        )
    ).scalar_one_or_none()


async def set_branch_promotion(
    db: AsyncSession,
    user_id: str,
    client_id: int,
    branch_id: int,
    promotion_id: int,
    is_enabled: bool,
) -> Branch_promotion_override:
    """Upsert a branch's enablement of one promotion (commits).

    One row per (client_id, branch_id, promotion_id): a second set updates the
    existing row's ``is_enabled`` flag rather than inserting a duplicate, so
    re-enabling a previously disabled promotion toggles the same row.
    """
    row = await _get_row(db, client_id, branch_id, promotion_id)
    if row is None:
        row = Branch_promotion_override(
            user_id=str(user_id),
            client_id=client_id,
            branch_id=branch_id,
            promotion_id=promotion_id,
            is_enabled=bool(is_enabled),
        )
        db.add(row)
    else:
        await db.execute(
            update(Branch_promotion_override)
            .where(Branch_promotion_override.id == row.id)
            .values(is_enabled=bool(is_enabled))
        )
    await db.commit()
    await db.refresh(row)
    return row


async def delete_branch_promotion(
    db: AsyncSession, client_id: int, branch_id: int, promotion_id: int
) -> bool:
    """Remove a branch override so the promotion falls back to running (enabled)."""
    row = await _get_row(db, client_id, branch_id, promotion_id)
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def _disabled_promotion_ids(
    db: AsyncSession, client_id: int, branch_id: int
) -> set:
    rows = (
        await db.execute(
            select(Branch_promotion_override.promotion_id).where(
                Branch_promotion_override.client_id == client_id,
                Branch_promotion_override.branch_id == branch_id,
                Branch_promotion_override.is_enabled.is_(False),
            )
        )
    ).scalars().all()
    return {int(pid) for pid in rows}


async def resolve_branch_promotions(
    db: AsyncSession, user_id: str, client_id: int, branch_id: int
) -> dict:
    """Resolve the promotions effective at a branch.

    Returns ``{"branch_id", "promotions", "disabled_promotion_ids"}``: every active
    chain promotion (owner-scoped, SEC-02) the branch has *not* opted out of, plus
    the sorted list of promotion ids the branch has disabled. ``promotions`` is a
    list of ``{promotion_id, name, kind}`` summaries.
    """
    disabled = await _disabled_promotion_ids(db, client_id, branch_id)
    active = await load_active_promotions(db, user_id)
    promotions = [
        {"promotion_id": p.id, "name": p.name, "kind": p.kind}
        for p in active
        if int(p.id) not in disabled
    ]
    return {
        "branch_id": branch_id,
        "promotions": promotions,
        "disabled_promotion_ids": sorted(disabled),
    }
