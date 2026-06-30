"""Cross-branch sales reporting (#220 multi-branch).

Rolls each branch's sales up side by side for a multi-location chain. Non-excluded
transactions (held/voided dropped, exactly like the financial reports) are grouped
by ``branch_id``; a credit note carries negative signed amounts (F-007), so a
signed SUM of ``total_amount`` nets refunds out per branch. Every read is scoped to
the caller's ``client_id`` (SEC-02), so one tenant's branches never appear in
another's report.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.branches import Branches
from models.transactions import Transactions

logger = logging.getLogger(__name__)


async def cross_branch_sales(
    db: AsyncSession,
    client_id: int,
    owner_id: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> dict:
    """Per-branch net sales + sale count for a client, plus chain-wide totals.

    Optional ``start``/``end`` bound the report by ``created_at`` (half-open
    ``[start, end)``); omit either to leave that side unbounded. Branches with no
    sales in the window are omitted. ``branch_id`` is ``None`` for sales rung up
    without a branch tag (single-branch / legacy rows), reported as "Unassigned".
    """
    filters = [
        Transactions.client_id == client_id,
        Transactions.status.is_distinct_from("held"),
        Transactions.status.is_distinct_from("voided"),
    ]
    if start is not None:
        filters.append(Transactions.created_at >= start)
    if end is not None:
        filters.append(Transactions.created_at < end)

    rows = (
        await db.execute(
            select(
                Transactions.branch_id,
                func.coalesce(func.sum(Transactions.total_amount), 0.0),
                func.count(Transactions.id),
            )
            .where(*filters)
            .group_by(Transactions.branch_id)
        )
    ).all()

    names = await _branch_names(db, owner_id)

    branches: List[dict] = []
    total_net_sales = 0.0
    total_sales_count = 0
    for branch_id, net_sales, sales_count in rows:
        net = round(float(net_sales or 0.0), 2)
        count = int(sales_count or 0)
        branches.append(
            {
                "branch_id": branch_id,
                "branch_name": names.get(branch_id, "Unassigned"),
                "net_sales": net,
                "sales_count": count,
            }
        )
        total_net_sales += net
        total_sales_count += count

    branches.sort(key=lambda b: b["net_sales"], reverse=True)
    return {
        "branches": branches,
        "total_net_sales": round(total_net_sales, 2),
        "total_sales_count": total_sales_count,
    }


async def _branch_names(db: AsyncSession, owner_id: str) -> Dict[int, str]:
    """Branches are owner-scoped (``user_id``), not client-scoped."""
    rows = (
        await db.execute(
            select(Branches.id, Branches.name).where(Branches.user_id == str(owner_id))
        )
    ).all()
    return {bid: name for bid, name in rows}
