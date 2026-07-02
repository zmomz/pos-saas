"""F-025 / AG-05+AG-06: deep white-label — agent custom domain + branded email.

Adds three columns to ``agents``:
- ``custom_domain`` (AG-05): the agent's own host; a request on this domain
  resolves the agent's branding so the merchant login/funnel is served under the
  agent's brand. Stored normalized for the by-domain lookup.
- ``email_template_subject`` / ``email_template_body`` (AG-06): the agent's
  optional branded provisioning-email template.

On a fresh database the baseline revision's ``create_all`` already builds the
``agents`` table at its current shape (with the new columns), so each add is
guarded idempotently — it only acts on a database migrated to head before this
revision existed. See finding F-025.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-06-04 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
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


def upgrade() -> None:
    insp = inspect(op.get_bind())
    _add_column_if_missing(insp, "agents", sa.Column("custom_domain", sa.String(), nullable=True))
    _add_column_if_missing(insp, "agents", sa.Column("email_template_subject", sa.String(), nullable=True))
    _add_column_if_missing(insp, "agents", sa.Column("email_template_body", sa.String(), nullable=True))


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop_column_if_present(insp, "agents", "email_template_body")
    _drop_column_if_present(insp, "agents", "email_template_subject")
    _drop_column_if_present(insp, "agents", "custom_domain")
