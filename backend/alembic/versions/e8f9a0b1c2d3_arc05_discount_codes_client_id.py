"""ARC-05: add ``discount_codes.client_id`` and backfill it from the owning client.

``DiscountCodes`` (single-use unique codes, ISSUE-059) was user-scoped only while
the core tables (products, transactions, …) also carry ``client_id``. That
asymmetry invited cross-tenant query mistakes whenever code joined or filtered on
``client_id``. This revision brings ``discount_codes`` in line (the third ARC-05
slice, after ``categories`` and ``discounts``): it adds the column, indexes it,
and backfills it for already-migrated databases by resolving each row's
``user_id`` to its owning client (the lowest-id ``clients`` row for that
``user_id`` — the same deterministic owner the tenancy resolver picks, SEC-12).

On a fresh database the model metadata already builds ``discount_codes`` with the
column (``create_all``), so the add is guarded to be idempotent and the backfill
simply finds no legacy rows.

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-06-27 14:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, Sequence[str], None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "discount_codes"
_COLUMN = "client_id"

# Backfill the tenant key from the owning client: a code's ``user_id`` is the
# owning merchant's id, and that merchant's client is the lowest-id ``clients``
# row for it (matching ``resolve_tenant_scope``'s deterministic owner).
_BACKFILL_SQL = sa.text(
    """
    UPDATE discount_codes
       SET client_id = (
            SELECT c.id FROM clients c
             WHERE c.user_id = discount_codes.user_id
             ORDER BY c.id ASC
             LIMIT 1
       )
     WHERE client_id IS NULL
       AND EXISTS (
            SELECT 1 FROM clients c WHERE c.user_id = discount_codes.user_id
       )
    """
)


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if _TABLE not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COLUMN not in existing:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.Integer(), nullable=True))
        op.create_index(f"ix_{_TABLE}_{_COLUMN}", _TABLE, [_COLUMN])
    # Backfill regardless: on a fresh DB the column pre-exists (create_all) but is
    # unpopulated, and there are no legacy rows so the UPDATE is a no-op.
    op.execute(_BACKFILL_SQL)


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if _TABLE not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COLUMN in existing:
        try:
            op.drop_index(f"ix_{_TABLE}_{_COLUMN}", table_name=_TABLE)
        except Exception:
            pass
        op.drop_column(_TABLE, _COLUMN)
