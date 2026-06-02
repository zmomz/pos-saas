"""Sync schema to the current ORM models (Phase 3 — migrations-on-boot).

Phases 2–6 added columns and tables at runtime (``create_all`` + ad-hoc
``ALTER TABLE``) rather than through migrations, so the hand-written chain up to
``d3e4f5a6b7c8`` lags the actual model definitions (e.g. ``transactions.branch_id``
/ ``shift_id`` / ``offline_id``, the client subscription columns, the
``product_branch_stock`` ledger, ``revoked_tokens``, ``subscription_payments``,
``branches`` …).

This revision squashes that drift: it imports every ORM model and runs
``Base.metadata.create_all`` (``checkfirst=True``), which creates any missing
tables at their *current* shape. The result is that ``alembic upgrade head`` on a
fresh database yields a schema identical to ``Base.metadata`` — so the
"autogenerate diff is empty" CI invariant holds and migrations-on-boot is safe to
enable. For an already-migrated database it is a no-op for existing tables.

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-06-02 23:55:00.000000
"""
import importlib
import pkgutil
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

import models
from core.database import Base

# revision identifiers, used by Alembic.
revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, Sequence[str], None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _load_all_models() -> None:
    """Import every model module so it registers on ``Base.metadata``."""
    for _, module_name, _ in pkgutil.iter_modules(models.__path__):
        importlib.import_module(f"{models.__name__}.{module_name}")


# Columns that Phases 2/4/5 added at runtime to tables the *earlier* hand-written
# migrations had already created at their old shape. ``create_all`` skips existing
# tables, so these must be added explicitly. Each entry is (table, Column). The
# add is guarded by an inspector check so it is idempotent on already-patched DBs.
_DRIFTED_COLUMNS = [
    ("clients", sa.Column("billing_cycle", sa.String(), server_default="monthly", nullable=True)),
    ("clients", sa.Column("subscription_status", sa.String(), server_default="active", nullable=True)),
    ("clients", sa.Column("next_billing_date", sa.String(), nullable=True)),
    ("transactions", sa.Column("shift_id", sa.Integer(), nullable=True)),
    ("transactions", sa.Column("branch_id", sa.Integer(), nullable=True)),
    ("transactions", sa.Column("offline_id", sa.String(), nullable=True)),
    ("zatca_documents", sa.Column("document_type", sa.String(), server_default="invoice", nullable=False)),
    ("audit_logs", sa.Column("entity_type", sa.String(), nullable=True)),
    ("audit_logs", sa.Column("entity_id", sa.String(), nullable=True)),
    ("audit_logs", sa.Column("changes", sa.String(), nullable=True)),
    ("agents", sa.Column("stripe_account_id", sa.String(), nullable=True)),
]


def upgrade() -> None:
    _load_all_models()
    bind = op.get_bind()
    # checkfirst=True: only creates tables that don't already exist.
    Base.metadata.create_all(bind=bind, checkfirst=True)

    # Fill in columns missing from tables created by earlier revisions.
    insp = inspect(bind)
    for table, column in _DRIFTED_COLUMNS:
        if table not in insp.get_table_names():
            continue
        existing = {c["name"] for c in insp.get_columns(table)}
        if column.name not in existing:
            op.add_column(table, column)


def downgrade() -> None:
    # No-op: this revision only fills in tables that prior revisions/runtime
    # bootstrapping never created. We never drop them on downgrade.
    pass
