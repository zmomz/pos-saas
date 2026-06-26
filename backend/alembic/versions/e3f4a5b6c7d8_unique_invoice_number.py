"""Atomic invoice counter backstop — unique (client_id, invoice_number) (DAT-05).

Fiscal numbers are minted with an atomic counter increment
(``services.invoice_counter.mint_invoice_number``); this unique constraint is the
last-line guard against a duplicate signed invoice/credit note ever reaching the
ledger. Existing rows are scanned for pre-existing duplicates first — if any are
found the migration aborts with the offending numbers so an operator can resolve
them, rather than silently failing to build the constraint.

On a fresh database the baseline ``create_all`` already builds the constraint
from the model, so the upgrade only acts when it is absent.

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-06-26 12:45:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, Sequence[str], None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT_NAME = "uq_transaction_client_invoice"


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
    # violates it (a pre-existing duplicate fiscal number must be reconciled by
    # hand before this guard can go on).
    dupes = bind.execute(
        sa.text(
            "SELECT client_id, invoice_number, COUNT(*) AS n "
            "FROM transactions "
            "WHERE invoice_number IS NOT NULL "
            "GROUP BY client_id, invoice_number HAVING COUNT(*) > 1"
        )
    ).fetchall()
    if dupes:
        listing = ", ".join(f"(client={r[0]}, {r[1]} x{r[2]})" for r in dupes[:20])
        raise RuntimeError(
            "DAT-05: cannot add unique (client_id, invoice_number) constraint — "
            f"{len(dupes)} pre-existing duplicate fiscal number(s): {listing}"
        )

    # SQLite cannot ALTER TABLE ADD CONSTRAINT, so batch mode recreates the table
    # with the constraint. Matches the model's table-level UniqueConstraint.
    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            CONSTRAINT_NAME, ["client_id", "invoice_number"]
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
