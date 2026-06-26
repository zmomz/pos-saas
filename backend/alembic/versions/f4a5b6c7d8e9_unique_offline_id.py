"""Offline-sale idempotency backstop — unique (client_id, offline_id) (DAT-06).

Offline-queued sales carry a client-generated ``offline_id`` and are deduplicated
on it when the device reconnects. Before DAT-06 the dedup was a SELECT-then-insert
with no DB constraint, so two concurrent syncs of the same ``offline_id`` could
both miss and both insert — a double-booked sale. This unique constraint makes the
database the arbiter; the sync path treats an insert-conflict as the idempotency
signal and returns the already-persisted sale.

NULL ``offline_id`` rows (live sales, held tickets, credit notes) are exempt — in
SQLite and Postgres NULLs are distinct, so non-offline rows never collide here.

Existing rows are scanned for a pre-existing duplicate first — if any are found the
migration aborts with the offending ids so an operator can reconcile them by hand,
rather than silently failing to build the constraint. On a fresh database the
baseline ``create_all`` already builds the constraint from the model, so the
upgrade only acts when it is absent.

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-06-26 13:20:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, Sequence[str], None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT_NAME = "uq_transaction_client_offline"


def _already_present(bind) -> bool:
    insp = inspect(bind)
    if "transactions" not in insp.get_table_names():
        return True  # nothing to do; the table will be built with the constraint
    try:
        uniques = insp.get_unique_constraints("transactions")
    except NotImplementedError:
        uniques = []
    if any(uc.get("name") == CONSTRAINT_NAME for uc in uniques):
        return True
    return any(ix["name"] == CONSTRAINT_NAME for ix in insp.get_indexes("transactions"))


def upgrade() -> None:
    bind = op.get_bind()
    if _already_present(bind):
        return

    # Pre-check: refuse to build a unique constraint over data that already
    # violates it (a pre-existing double-booked offline_id must be reconciled by
    # hand before this guard can go on). NULL offline_ids are excluded — they are
    # exempt from the constraint.
    dupes = bind.execute(
        sa.text(
            "SELECT client_id, offline_id, COUNT(*) AS n "
            "FROM transactions "
            "WHERE offline_id IS NOT NULL "
            "GROUP BY client_id, offline_id HAVING COUNT(*) > 1"
        )
    ).fetchall()
    if dupes:
        listing = ", ".join(f"(client={r[0]}, {r[1]} x{r[2]})" for r in dupes[:20])
        raise RuntimeError(
            "DAT-06: cannot add unique (client_id, offline_id) constraint — "
            f"{len(dupes)} pre-existing duplicate offline sale(s): {listing}"
        )

    # SQLite cannot ALTER TABLE ADD CONSTRAINT, so batch mode recreates the table
    # with the constraint. Matches the model's table-level UniqueConstraint.
    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            CONSTRAINT_NAME, ["client_id", "offline_id"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "transactions" not in insp.get_table_names():
        return
    try:
        uniques = {uc.get("name") for uc in insp.get_unique_constraints("transactions")}
    except NotImplementedError:
        uniques = set()
    if CONSTRAINT_NAME in uniques:
        with op.batch_alter_table("transactions", schema=None) as batch_op:
            batch_op.drop_constraint(CONSTRAINT_NAME, type_="unique")
