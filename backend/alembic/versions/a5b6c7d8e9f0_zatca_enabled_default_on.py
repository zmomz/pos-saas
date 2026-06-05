"""F-022 / ZA-09: honor per-client zatca_enabled, default it ON, backfill existing.

The ``clients.zatca_enabled`` flag historically defaulted to ``False`` and was set
``False`` at provisioning, but the sale path **never read it** — every sale was
signed regardless. F-022 makes the flag authoritative
(``services/zatca_sale.py::is_zatca_enabled``): an explicit ``False`` now disables
e-invoicing for that client.

To avoid silently turning ZATCA *off* for every existing merchant (which was being
signed in practice), this migration:

* flips the column's ``server_default`` to ``'true'`` so newly created rows default ON, and
* backfills every existing row that is not already ``True`` (the de-facto-signed
  ``False``/NULL rows) to ``True`` — preserving the always-signed behavior those
  clients had before the flag was honored.

Idempotent: guarded on the table existing; the backfill only touches non-True
rows, so re-running is a no-op. On a fresh database the baseline ``create_all``
already builds ``clients`` with the new ON default, so only the backfill runs (and
matches nothing).

Revision ID: a5b6c7d8e9f0
Revises: a4b5c6d7e8f9
Create Date: 2026-06-05 10:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "a5b6c7d8e9f0"
down_revision: Union[str, Sequence[str], None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "clients" not in insp.get_table_names():
        return
    columns = {c["name"] for c in insp.get_columns("clients")}
    if "zatca_enabled" not in columns:
        return

    # Flip the stored default ON for new rows.
    with op.batch_alter_table("clients") as batch_op:
        batch_op.alter_column(
            "zatca_enabled",
            existing_type=sa.Boolean(),
            server_default=sa.text("'true'"),
            existing_nullable=True,
        )

    # Backfill de-facto-signed rows (False / NULL) to enabled so honoring the
    # flag does not disable ZATCA for clients that were being signed all along.
    op.execute(
        "UPDATE clients SET zatca_enabled = 1 "
        "WHERE zatca_enabled IS NULL OR zatca_enabled = 0"
    )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "clients" not in insp.get_table_names():
        return
    columns = {c["name"] for c in insp.get_columns("clients")}
    if "zatca_enabled" not in columns:
        return
    with op.batch_alter_table("clients") as batch_op:
        batch_op.alter_column(
            "zatca_enabled",
            existing_type=sa.Boolean(),
            server_default=sa.text("'false'"),
            existing_nullable=True,
        )
