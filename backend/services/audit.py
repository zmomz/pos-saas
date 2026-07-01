"""Audit-trail writer + tamper-evidence (ISSUE-019).

The ``audit_logs`` table existed as CRUD-only scaffolding that was never written
automatically on mutations. ``write_audit_log`` is a best-effort helper that
persists one row in its own session so a logging failure can never break (or roll
back) the request it is recording.

The store is a compliance trail, so it is append-only and tamper-evident: each
row is linked to the prior one by a SHA-256 chain (``prev_hash`` -> ``row_hash``).
``verify_audit_chain`` re-walks the chain and reports the first row whose content
was mutated or whose predecessor was removed. There is no application path that
updates or deletes an existing row.
"""
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import db_manager
from models.audit_logs import Audit_logs

logger = logging.getLogger(__name__)

# Seed for the very first row's ``prev_hash`` — a fixed, well-known constant so a
# verifier can re-derive the chain head without trusting any stored value.
GENESIS_HASH = "0" * 64


def _canonical_content(row) -> str:
    """Stable, order-fixed serialization of a row's immutable content.

    Covers exactly the fields written at insert time (not ``id``/``updated_at``,
    which are storage/bookkeeping), so re-hashing a row reproduces its
    ``row_hash`` iff none of its content changed.
    """
    created_at = row.created_at
    return json.dumps(
        {
            "user_id": row.user_id,
            "owner_user_id": row.owner_user_id,
            "action": row.action,
            "details": row.details,
            "ip_address": row.ip_address,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "changes": row.changes,
            "created_at": created_at.isoformat() if isinstance(created_at, datetime) else created_at,
        },
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )


def compute_row_hash(prev_hash: str, row) -> str:
    """Chain hash for ``row``: sha256(prev_hash + canonical content)."""
    payload = (prev_hash or GENESIS_HASH) + _canonical_content(row)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def write_audit_log(
    user_id: str,
    action: str,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    changes: Optional[str] = None,
) -> None:
    """Persist a single chained audit row. Never raises — failures are logged and swallowed."""
    if not db_manager.async_session_maker:
        return
    try:
        from dependencies.tenancy import resolve_owner_user_id

        async with db_manager.async_session_maker() as db:
            # Tag the row with the owning merchant (resolved via the tenant scope)
            # so a merchant's audit query surfaces all staff activity, not only the
            # actor's own actions (finding H4). ``anonymous`` failed-auth rows have
            # no resolvable owner.
            owner_user_id = (
                await resolve_owner_user_id(db, user_id)
                if user_id and user_id != "anonymous"
                else None
            )
            row = Audit_logs(
                user_id=str(user_id),
                owner_user_id=owner_user_id,
                action=action,
                details=(details or "")[:2000] or None,
                ip_address=ip_address,
                entity_type=entity_type,
                entity_id=(str(entity_id) if entity_id is not None else None),
                changes=(changes or "")[:4000] or None,
                # Pin created_at in Python so it is part of the hashed content
                # (the column default would otherwise fill it after we hash).
                created_at=datetime.now(),
            )
            # Link onto the current chain head. The most recent hashed row's
            # ``row_hash`` is this row's ``prev_hash``; the first ever row seeds
            # from GENESIS_HASH.
            head = await db.execute(
                select(Audit_logs.row_hash)
                .where(Audit_logs.row_hash.is_not(None))
                .order_by(Audit_logs.id.desc())
                .limit(1)
            )
            row.prev_hash = head.scalar_one_or_none() or GENESIS_HASH
            row.row_hash = compute_row_hash(row.prev_hash, row)
            db.add(row)
            await db.commit()
    except Exception as exc:  # pragma: no cover - defensive; auditing must not break requests
        logger.warning("Failed to write audit log (%s): %s", action, exc)


@dataclass
class AuditChainResult:
    """Outcome of re-walking the audit hash chain."""

    ok: bool
    broken_id: Optional[int] = None
    reason: Optional[str] = None  # "content_tampered" | "broken_link"
    checked: int = 0


async def verify_audit_chain(db: AsyncSession) -> AuditChainResult:
    """Re-walk the audit chain in insertion order and report the first break.

    Detects two tamper modes:
    * ``content_tampered`` — a row's stored ``row_hash`` no longer matches a
      re-hash of its content (a field was edited in place);
    * ``broken_link`` — a row's ``prev_hash`` doesn't match the prior row's
      ``row_hash`` (a row was removed, reordered, or re-parented).
    """
    result = await db.execute(select(Audit_logs).order_by(Audit_logs.id.asc()))
    rows = result.scalars().all()

    expected_prev = GENESIS_HASH
    checked = 0
    for row in rows:
        if row.row_hash is None:
            # Pre-ISSUE-019 row with no chain hash; not part of the chain.
            continue
        stored_prev = row.prev_hash or GENESIS_HASH
        if stored_prev != expected_prev:
            return AuditChainResult(False, row.id, "broken_link", checked)
        if compute_row_hash(stored_prev, row) != row.row_hash:
            return AuditChainResult(False, row.id, "content_tampered", checked)
        expected_prev = row.row_hash
        checked += 1

    return AuditChainResult(True, None, None, checked)


# The export artifact's schema version, bumped when its shape changes so an
# external verifier can key its parser off a stable field.
REGULATORY_EXPORT_FORMAT_VERSION = "1.0"


def _export_record(row: Audit_logs) -> dict:
    """The raw compliance content of one audit row, including its chain hashes.

    Unlike the AuditLog read-projection (which normalizes ``action`` to a verb and
    resolves the actor email for display), the regulatory artifact carries the
    stored fields verbatim plus ``prev_hash``/``row_hash`` so an external auditor
    can independently re-derive ``compute_row_hash`` and re-walk the chain.
    """
    return {
        "id": row.id,
        "user_id": row.user_id,
        "owner_user_id": row.owner_user_id,
        "action": row.action,
        "details": row.details,
        "ip_address": row.ip_address,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "changes": row.changes,
        "prev_hash": row.prev_hash,
        "row_hash": row.row_hash,
        "created_at": row.created_at,
    }


async def build_regulatory_audit_export(
    db: AsyncSession, owner_user_id: Optional[str] = None
) -> dict:
    """Build a self-describing, independently verifiable audit-trail artifact.

    Owner-scoped (SEC-02): a tenant caller (``owner_user_id`` set) gets only their
    own rows; the platform master (``None``) gets the whole store. The artifact
    surfaces the *reconcile status* — the outcome of ``verify_audit_chain`` over
    the (globally chained) store — so it attests whether the trail is intact.
    """
    query = select(Audit_logs).order_by(Audit_logs.id.asc())
    if owner_user_id:
        query = query.where(Audit_logs.owner_user_id == owner_user_id)
    rows = (await db.execute(query)).scalars().all()

    # The hash chain links every row across the store, so integrity is a
    # store-wide attestation (re-walked over the full chain, not the scoped slice).
    chain = await verify_audit_chain(db)

    return {
        "artifact_type": "regulatory_audit_export",
        "format_version": REGULATORY_EXPORT_FORMAT_VERSION,
        "generated_at": datetime.now(),
        "owner_user_id": owner_user_id,
        "record_count": len(rows),
        "integrity": {
            "verified": chain.ok,
            "checked": chain.checked,
            "broken_id": chain.broken_id,
            "reason": chain.reason,
        },
        "records": [_export_record(r) for r in rows],
    }
