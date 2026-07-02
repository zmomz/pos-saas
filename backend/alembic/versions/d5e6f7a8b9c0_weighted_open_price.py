"""F-011 / POS-11: weighted & open-price items.

Two changes to the catalog so the POS can sell weighted (fractional-quantity) and
open-price (price-entered-at-sale) products:

- ``products.is_weighted`` / ``products.is_open_price`` (Boolean) + an optional
  ``products.unit_label`` (e.g. "kg") — the product-level configuration that drives
  the POS behaviour and excludes an open-price line from the ``pos.price_override``
  fraud gate (POS-08).
- ``products.quantity`` and ``product_branch_stock.quantity`` widened from Integer
  to Float so a weighted product's on-hand stock tracks fractional amounts.

On a fresh database the baseline revision's ``create_all`` already builds both
tables at their current (Float + flag) shape, so the column adds are guarded to be
idempotent and the type widening is a no-op there. The Integer→Float widening is
only meaningful on an already-migrated database; SQLite is dynamically typed (and
the fresh-DB shape is already Float), so the widening is applied on non-SQLite
backends (Postgres) only. See finding F-011.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-06-04 13:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(insp, table: str, column: sa.Column) -> None:
    if table not in insp.get_table_names():
        # Fresh DB: the baseline revision's create_all already built the table at
        # its current shape (with the new column). Nothing to backfill.
        return
    existing = {c["name"] for c in insp.get_columns(table)}
    if column.name not in existing:
        op.add_column(table, column)


def _drop_column_if_present(insp, table: str, column: str) -> None:
    if table in insp.get_table_names():
        existing = {c["name"] for c in insp.get_columns(table)}
        if column in existing:
            # Drop any index covering this column first — SQLite rejects a
            # DROP COLUMN while an index still references it (the column can be
            # indexed via the ORM's ``index=True`` baked into a create_table).
            # Re-inspect live so an index a prior step already dropped is not
            # dropped twice (a passed-in inspector may be stale).
            for idx in inspect(op.get_bind()).get_indexes(table):
                if column in (idx.get("column_names") or []):
                    op.drop_index(idx["name"], table_name=table)
            op.drop_column(table, column)


def _quantity_column(insp, table: str):
    if table not in insp.get_table_names():
        return None
    return next((c for c in insp.get_columns(table) if c["name"] == "quantity"), None)


def _alter_quantity_type(insp, table: str, type_, existing_type) -> None:
    """Widen/narrow ``<table>.quantity`` idempotently.

    Uses ``batch_alter_table`` so the change works on SQLite (which cannot ALTER
    COLUMN TYPE in place) as well as Postgres. Skips when the column is already the
    target type (e.g. a fresh DB whose ``create_all`` baseline already built it),
    keeping the autogenerate-diff invariant and avoiding a needless table rebuild.
    """
    col = _quantity_column(insp, table)
    if col is None or isinstance(col["type"], type_.__class__):
        return
    with op.batch_alter_table(table) as batch_op:
        batch_op.alter_column(
            "quantity",
            type_=type_,
            existing_type=existing_type,
            existing_nullable=col["nullable"],
        )


def upgrade() -> None:
    insp = inspect(op.get_bind())
    _add_column_if_missing(
        insp,
        "products",
        sa.Column("is_weighted", sa.Boolean(), nullable=True, server_default="false"),
    )
    _add_column_if_missing(
        insp,
        "products",
        sa.Column("is_open_price", sa.Boolean(), nullable=True, server_default="false"),
    )
    _add_column_if_missing(
        insp,
        "products",
        sa.Column("unit_label", sa.String(), nullable=True),
    )
    _alter_quantity_type(insp, "products", sa.Float(), sa.Integer())
    _alter_quantity_type(insp, "product_branch_stock", sa.Float(), sa.Integer())


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _alter_quantity_type(insp, "products", sa.Integer(), sa.Float())
    _alter_quantity_type(insp, "product_branch_stock", sa.Integer(), sa.Float())
    _drop_column_if_present(insp, "products", "unit_label")
    _drop_column_if_present(insp, "products", "is_open_price")
    _drop_column_if_present(insp, "products", "is_weighted")
