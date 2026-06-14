"""ISSUE-019 — append-only / tamper-evident audit log.

The audit store is a compliance trail: ``services.audit.write_audit_log`` is its
sole writer, and every row is linked to the prior one by a SHA-256 chain
(``prev_hash`` -> ``row_hash``). ``verify_audit_chain`` re-walks the chain so a
tampered or removed row is detectable.
"""
from sqlalchemy import select, update, delete

from core.database import db_manager
from models.audit_logs import Audit_logs
from services.audit import write_audit_log, verify_audit_chain
from services.audit_logs import Audit_logsService


async def _all_rows():
    async with db_manager.async_session_maker() as db:
        result = await db.execute(select(Audit_logs).order_by(Audit_logs.id.asc()))
        return result.scalars().all()


async def test_written_rows_form_a_verifiable_chain():
    # AC2/AC3: a run of writes leaves a chain that verifies clean.
    for n in range(3):
        await write_audit_log(user_id="anonymous", action=f"TEST_CHAIN {n}")

    async with db_manager.async_session_maker() as db:
        result = await verify_audit_chain(db)
    assert result.ok, result

    rows = await _all_rows()
    # Every row carries a populated chaining hash linking it to the prior row.
    assert all(r.row_hash for r in rows)
    for prev, cur in zip(rows, rows[1:]):
        assert cur.prev_hash == prev.row_hash


async def test_editing_a_rows_content_breaks_verification():
    # AC2/AC3: mutating a stored row's content (without re-chaining) is detectable.
    await write_audit_log(user_id="anonymous", action="TAMPER_TARGET")
    target = (await _all_rows())[-1]

    # Mutate inside an uncommitted transaction: verification (same session,
    # autoflush) sees the edit, but the persistent chain is rolled back clean so
    # the shared test DB isn't poisoned for later tests.
    async with db_manager.async_session_maker() as db:
        await db.execute(
            update(Audit_logs).where(Audit_logs.id == target.id).values(action="EDITED")
        )
        result = await verify_audit_chain(db)
        await db.rollback()

    assert not result.ok
    assert result.broken_id == target.id
    assert result.reason == "content_tampered"


async def test_removing_a_row_breaks_the_link():
    # AC2/AC3: deleting a middle row severs the chain at its successor.
    for n in range(3):
        await write_audit_log(user_id="anonymous", action=f"REMOVE_SEQ {n}")
    first, middle, last = (await _all_rows())[-3:]

    # Remove inside an uncommitted transaction (see the tamper test): the chain is
    # restored on rollback so this destructive probe doesn't corrupt the shared DB.
    async with db_manager.async_session_maker() as db:
        await db.execute(delete(Audit_logs).where(Audit_logs.id == middle.id))
        result = await verify_audit_chain(db)
        await db.rollback()

    assert not result.ok
    # The successor's prev_hash now points at a row that is no longer present.
    assert result.broken_id == last.id
    assert result.reason == "broken_link"


def test_audit_service_exposes_no_mutation_path():
    # AC1: audit rows are write-once — the read service offers no update/delete/
    # create path (the sole writer is services.audit.write_audit_log).
    for forbidden in ("create", "update", "delete"):
        assert not hasattr(Audit_logsService, forbidden), forbidden
