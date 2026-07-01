"""Operator tenant-migration service (M10 Admin, #225).

The platform master's control-plane version of the agent self-serve transfer
(``routers/tenant.py::transfer_client``): move any merchant (``Clients`` row)
from one owning agent to another. The master is not an owning agent, so the
agent-scoped endpoint — which 403s non-agents and only ever touches the caller's
*own* book — cannot serve this; operators need to migrate *any* tenant between
*any* two agents.

The accounting is identical to the agent transfer so the two paths can never
disagree: slots move with the merchant. A slot is atomically acquired on the
destination first (fail closed if that agent is full — never oversell), then
freed on the source. A slot is only in play for a *live* merchant; an archived
one already returned its slot on archive, so nothing is acquired or freed for it.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.agents import Agents
from models.audit_logs import Audit_logs
from models.clients import Clients

logger = logging.getLogger(__name__)


async def _acquire_agent_slot(db: AsyncSession, agent_id: int) -> bool:
    """Atomically deduct one client slot from an agent's quota (MA-02).

    Mirrors ``routers/tenant.py::_acquire_agent_slot`` — the guarded UPDATE only
    succeeds while a slot is free, so a migration can never oversell a package.
    Returns True when a slot was taken, False when the agent is at capacity.
    """
    result = await db.execute(
        update(Agents)
        .where(
            Agents.id == agent_id,
            func.coalesce(Agents.used_slots, 0) < Agents.package_type,
        )
        .values(used_slots=func.coalesce(Agents.used_slots, 0) + 1)
    )
    return result.rowcount > 0


async def _free_agent_slot(db: AsyncSession, agent_id: int) -> None:
    """Return one client slot to an agent's quota, never dropping below zero."""
    await db.execute(
        update(Agents)
        .where(Agents.id == agent_id, func.coalesce(Agents.used_slots, 0) > 0)
        .values(used_slots=Agents.used_slots - 1)
    )


async def migrate_tenant(
    db: AsyncSession,
    *,
    client_id: int,
    target_agent_id: int | None = None,
    target_agent_email: str | None = None,
    actor_user_id: str | None = None,
) -> dict:
    """Migrate merchant ``client_id`` to a destination agent (master control plane).

    Raises :class:`HTTPException` with a specific status on every refusal so the
    console surfaces *why* rather than silently corrupting ownership:

    * 404 — unknown merchant or unknown destination agent
    * 400 — neither a target id nor email supplied, or destination == source
    * 409 — destination agent suspended, or has no free slot (no oversell)

    Returns ``{success, client_id, from_agent_id, to_agent_id}``.
    """
    merchant = (
        await db.execute(select(Clients).where(Clients.id == client_id))
    ).scalar_one_or_none()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    if target_agent_id is not None:
        target_q = select(Agents).where(Agents.id == target_agent_id)
    elif target_agent_email:
        target_q = select(Agents).where(
            func.lower(Agents.email) == target_agent_email.strip().lower()
        )
    else:
        raise HTTPException(
            status_code=400, detail="target_agent_id or target_agent_email is required"
        )
    target_agent = (await db.execute(target_q)).scalar_one_or_none()
    if not target_agent:
        raise HTTPException(status_code=404, detail="Destination agent not found")

    source_agent_id = merchant.agent_id
    if target_agent.id == source_agent_id:
        raise HTTPException(status_code=400, detail="Merchant already belongs to this agent")
    if target_agent.is_active is False:
        raise HTTPException(status_code=409, detail="Destination agent is suspended")

    # An archived merchant holds no slot on the source (archive freed it), so only
    # move a slot when the merchant is live.
    is_live = not merchant.archived_at
    if is_live and not await _acquire_agent_slot(db, target_agent.id):
        raise HTTPException(
            status_code=409, detail="Destination agent has no available client slots."
        )

    await db.execute(
        update(Clients).where(Clients.id == client_id).values(agent_id=target_agent.id)
    )
    if is_live:
        await _free_agent_slot(db, source_agent_id)
    db.add(
        Audit_logs(
            user_id=actor_user_id,
            action="ADMIN_MIGRATE_TENANT",
            entity_type="clients",
            entity_id=str(client_id),
            details=(
                f"Master migrated merchant {client_id} ({merchant.email}) "
                f"from agent {source_agent_id} to agent {target_agent.id} "
                f"({target_agent.email})"
            ),
        )
    )
    await db.commit()
    return {
        "success": True,
        "client_id": client_id,
        "from_agent_id": source_agent_id,
        "to_agent_id": target_agent.id,
    }
