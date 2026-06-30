"""Per-branch staff access scoping (#220 multi-branch: branch permissions).

A chain's staff member may be scoped to a subset of its branches. The rule is
permissive-by-default so existing single-branch installs keep working:

* a staff member with **no** grants has *chain-wide* access (every branch);
* the first grant flips them to *scoped* — reachable only at the granted branches;
* revoking the last grant restores chain-wide access.

Every read/write is scoped to the caller's ``client_id`` (SEC-02), so one
tenant's branch grants never leak into — or out of — another's.
"""
import logging
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.staff_branch_access import Staff_branch_access

logger = logging.getLogger(__name__)


async def _get_row(
    db: AsyncSession, client_id: int, staff_id: int, branch_id: int
) -> Staff_branch_access | None:
    return (
        await db.execute(
            select(Staff_branch_access).where(
                Staff_branch_access.client_id == client_id,
                Staff_branch_access.staff_id == staff_id,
                Staff_branch_access.branch_id == branch_id,
            )
        )
    ).scalar_one_or_none()


async def list_staff_branches(
    db: AsyncSession, client_id: int, staff_id: int
) -> List[int]:
    """Return the branch ids the staff member is explicitly granted (sorted).

    An empty list means *unscoped* — chain-wide access (see ``is_scoped``).
    """
    rows = (
        await db.execute(
            select(Staff_branch_access.branch_id).where(
                Staff_branch_access.client_id == client_id,
                Staff_branch_access.staff_id == staff_id,
            )
        )
    ).scalars().all()
    return sorted(rows)


async def is_scoped(db: AsyncSession, client_id: int, staff_id: int) -> bool:
    """True once the staff member carries at least one branch grant."""
    return bool(await list_staff_branches(db, client_id, staff_id))


async def assign_branch(
    db: AsyncSession, user_id: str, client_id: int, staff_id: int, branch_id: int
) -> Staff_branch_access:
    """Grant the staff member access to a branch (commits, idempotent upsert).

    One row per (client_id, staff_id, branch_id): a repeat assignment returns the
    existing grant rather than inserting a duplicate.
    """
    row = await _get_row(db, client_id, staff_id, branch_id)
    if row is None:
        row = Staff_branch_access(
            user_id=str(user_id),
            client_id=client_id,
            staff_id=staff_id,
            branch_id=branch_id,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


async def revoke_branch(
    db: AsyncSession, client_id: int, staff_id: int, branch_id: int
) -> bool:
    """Remove a branch grant. Returns False when there was nothing to remove."""
    row = await _get_row(db, client_id, staff_id, branch_id)
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def has_branch_access(
    db: AsyncSession, client_id: int, staff_id: int, branch_id: int
) -> bool:
    """Whether the staff member may act at ``branch_id``.

    Unscoped (no grants) ⇒ access to *every* branch; scoped ⇒ only the branches
    explicitly granted.
    """
    branches = await list_staff_branches(db, client_id, staff_id)
    if not branches:
        return True
    return branch_id in branches
