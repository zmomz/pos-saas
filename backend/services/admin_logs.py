"""Platform-master log viewer (M10 Admin, #225).

The admin console's read-only **error/API log viewer**. Unlike the tenant-facing
``api_usage`` query (``routers/api_usage.py``), which is scoped to the caller's
own tenant, this surfaces the per-request log **platform-wide** — every tenant's
requests — because the operator running the platform needs to see them all.

It is strictly read-only: the ``api_usage`` rows are written by the request
middleware (:mod:`middlewares.production`); nothing here fabricates or mutates a
row. ``errors_only`` narrows to failing requests (``status_code >= 400``), which
is the "error log" view operators reach for.
"""
from typing import Any, Dict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.api_usage import Api_usage

# Anything at or above this status code is a failed request — the "error log".
ERROR_STATUS_FLOOR = 400


def _render(row: Api_usage) -> Dict[str, Any]:
    """Project a stored ``api_usage`` row to the shape the log viewer renders."""
    return {
        "id": row.id,
        "user_id": row.user_id,
        "owner_user_id": row.owner_user_id,
        "endpoint": row.endpoint,
        "method": row.method,
        "status_code": row.status_code,
        "response_time_ms": row.response_time_ms,
        "created_at": row.created_at,
    }


async def list_api_logs(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
    errors_only: bool = False,
) -> Dict[str, Any]:
    """Read the per-request API log platform-wide, newest-first and paginated.

    ``errors_only`` restricts to rows whose ``status_code >= 400``. No tenant
    filter is applied — this is a master-only surface (the caller is gated in the
    router), so it deliberately spans every tenant.
    """
    query = select(Api_usage)
    count_query = select(func.count(Api_usage.id))

    if errors_only:
        query = query.where(Api_usage.status_code >= ERROR_STATUS_FLOOR)
        count_query = count_query.where(Api_usage.status_code >= ERROR_STATUS_FLOOR)

    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(Api_usage.id.desc()).offset(skip).limit(limit)
    rows = (await db.execute(query)).scalars().all()

    return {
        "items": [_render(r) for r in rows],
        "total": total,
        "skip": skip,
        "limit": limit,
    }
