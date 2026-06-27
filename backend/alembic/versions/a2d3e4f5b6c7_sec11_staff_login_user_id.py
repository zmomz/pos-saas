"""SEC-11: bind staff identity via Staff_members.login_user_id (FK), not email.

Tenancy/permission resolution used to map a logged-in account to its owning
merchant by matching the *mutable* ``User.email`` against ``Staff_members.email``
— a string join an attacker could hijack by pre-registering a soon-to-be-staff
address. The fix resolves on a new immutable ``staff_members.login_user_id``
column (the staff member's own login id).

This revision adds the column and backfills it for already-migrated databases by
matching the staff row's ``email`` to a ``users.email`` whose id is *not* the
owning merchant (``user_id``). The backfill reproduces the historical email link
only for rows that already existed — it does not weaken the new contract, under
which fresh provisioning sets the FK directly and refuses to bind a pre-existing
(unverified) account.

On a fresh database the baseline revision's ``create_all`` already builds
``staff_members`` at its current shape (with the column), so the add is guarded to
be idempotent and the backfill simply finds no legacy rows.

Revision ID: a2d3e4f5b6c7
Revises: a1c2e3d4f5b6
Create Date: 2026-06-27 02:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "a2d3e4f5b6c7"
down_revision: Union[str, Sequence[str], None] = "a1c2e3d4f5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "staff_members"
_COLUMN = "login_user_id"

# Backfill the FK from the historical email link: a staff row's email that maps
# to a distinct user (not the owning merchant) was the cashier's own login.
_BACKFILL_SQL = sa.text(
    """
    UPDATE staff_members
       SET login_user_id = (
            SELECT u.id FROM users u
             WHERE u.email = staff_members.email
               AND u.id != staff_members.user_id
             LIMIT 1
       )
     WHERE login_user_id IS NULL
       AND email IS NOT NULL
       AND EXISTS (
            SELECT 1 FROM users u
             WHERE u.email = staff_members.email
               AND u.id != staff_members.user_id
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
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(), nullable=True))
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
