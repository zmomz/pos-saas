"""Aggregator/omnichannel idempotency backstop — unique
(client_id, provider, external_order_id) on channel_orders (DAT-07).

The aggregator webhook ingest (F-060) mints a ZATCA-signed invoice per delivery
order and deduplicates on (client_id, provider, external_order_id). Before DAT-07
the dedup was a SELECT-then-insert with no DB constraint, and the idempotency row was
written *after* the fiscal settle — so a crash between minting the signed invoice and
recording the claim, or a concurrent re-delivery racing past the SELECT, could mint a
**second signed invoice**. The ingest now claims the order (inserts status="received")
before settling; this unique constraint makes the database the arbiter so the loser's
insert conflicts and is treated as the duplicate.

Existing rows are scanned for a pre-existing duplicate first — if any are found the
migration aborts with the offending keys so an operator can reconcile them by hand,
rather than silently failing to build the constraint. On a fresh database the baseline
``create_all`` already builds the constraint from the model, so the upgrade only acts
when it is absent.

Revision ID: f9a0b1c2d3e4
Revises: f4a5b6c7d8e9
Create Date: 2026-06-26 13:40:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "f9a0b1c2d3e4"
down_revision: Union[str, Sequence[str], None] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT_NAME = "uq_channel_order_client_provider_ext"


def _already_present(bind) -> bool:
    insp = inspect(bind)
    if "channel_orders" not in insp.get_table_names():
        return True  # nothing to do; the table will be built with the constraint
    try:
        uniques = insp.get_unique_constraints("channel_orders")
    except NotImplementedError:
        uniques = []
    if any(uc.get("name") == CONSTRAINT_NAME for uc in uniques):
        return True
    return any(ix["name"] == CONSTRAINT_NAME for ix in insp.get_indexes("channel_orders"))


def upgrade() -> None:
    bind = op.get_bind()
    if _already_present(bind):
        return

    # Pre-check: refuse to build a unique constraint over data that already violates
    # it (a pre-existing double-booked order must be reconciled by hand first).
    dupes = bind.execute(
        sa.text(
            "SELECT client_id, provider, external_order_id, COUNT(*) AS n "
            "FROM channel_orders "
            "GROUP BY client_id, provider, external_order_id HAVING COUNT(*) > 1"
        )
    ).fetchall()
    if dupes:
        listing = ", ".join(f"(client={r[0]}, {r[1]}:{r[2]} x{r[3]})" for r in dupes[:20])
        raise RuntimeError(
            "DAT-07: cannot add unique (client_id, provider, external_order_id) "
            f"constraint — {len(dupes)} pre-existing duplicate channel order(s): {listing}"
        )

    # SQLite cannot ALTER TABLE ADD CONSTRAINT, so batch mode recreates the table
    # with the constraint. Matches the model's table-level UniqueConstraint.
    with op.batch_alter_table("channel_orders", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            CONSTRAINT_NAME, ["client_id", "provider", "external_order_id"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "channel_orders" not in insp.get_table_names():
        return
    try:
        uniques = {uc.get("name") for uc in insp.get_unique_constraints("channel_orders")}
    except NotImplementedError:
        uniques = set()
    if CONSTRAINT_NAME in uniques:
        with op.batch_alter_table("channel_orders", schema=None) as batch_op:
            batch_op.drop_constraint(CONSTRAINT_NAME, type_="unique")
