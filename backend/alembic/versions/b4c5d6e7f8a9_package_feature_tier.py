"""F-024 / MA-07: package feature-entitlement tier.

Adds the columns backing a package's feature tier (which features a package
unlocks) and the agent→package link used to derive a client's tier on
provisioning:

- ``packages.features`` — a JSON-encoded list of the feature keys the package
  unlocks (the enabled set). NULL ⇒ the package defines no tier and does not
  restrict features. See ``services/packages.py::normalize_feature_tier``.
- ``agents.package_id`` — the package an agent was provisioned from, so client
  provisioning can read ``packages.features`` and seed ``client_features``
  accordingly. NULL when the agent was created with an explicit slot count.

On a fresh database the baseline revision's ``create_all`` already builds the
tables at their current shape (with the new columns), so each add is guarded to
be idempotent — it only acts on a database migrated to head before this revision
existed. See finding F-024.

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-06-04 15:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, Sequence[str], None] = "a3b4c5d6e7f8"
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
            op.drop_column(table, column)


def upgrade() -> None:
    insp = inspect(op.get_bind())
    _add_column_if_missing(
        insp,
        "packages",
        sa.Column("features", sa.String(), nullable=True),
    )
    _add_column_if_missing(
        insp,
        "agents",
        sa.Column("package_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop_column_if_present(insp, "agents", "package_id")
    _drop_column_if_present(insp, "packages", "features")
