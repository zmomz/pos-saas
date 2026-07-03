"""ARC-05 sweep: guarantee ``client_id`` on every model that declares it.

Background
----------
The tenancy key ``client_id`` was retro-fitted onto entity tables in a series of
per-table ARC-05 revisions (``categories``, ``discounts``, ``expenses``,
``promotions``, ``customers``, ``discount_codes`` …). Meanwhile many *newer*
models (the restaurant vertical — ``modifiers``/``combos``/``kds_tickets``/…, the
branch-override tables, ``product_branch_*``, ``store_credit_ledger``,
``subscription_payments`` …) grew a ``client_id`` column that is only ever
materialised through ``Base.metadata.create_all`` at the
``e4f5a6b7c8d9`` baseline. That is fine for a *fresh* ``alembic upgrade head``
(create_all builds each table at its current shape, ``client_id`` included) — but
on an **already-baselined** database (the migration path used in prod, OPS-01,
where ``create_all`` is skipped) any ``client_id`` added to a model *after* that
DB was baselined never lands, and the entity endpoint 500s with
``no such column: <table>.client_id``.

This revision closes that gap once and for all: it walks every table that the
current ORM says should carry ``client_id`` and, guarded by a live inspector so
it is fully idempotent, adds the column + index wherever it is missing. Where the
table also carries a ``user_id`` (the owning merchant, per ``resolve_tenant_scope``
SEC-12) it backfills ``client_id`` from the lowest-id ``clients`` row for that
user — the same deterministic owner the earlier ARC-05 slices used.

On a fresh database (``client_id`` already present via create_all) every add is
skipped and each backfill finds only already-populated / owner-less rows, so the
whole revision is a no-op. On a drifted database it heals the schema.

Revision ID: c11d5f1xed01
Revises: 5defecb7cf98
Create Date: 2026-07-03 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "c11d5f1xed01"
down_revision: Union[str, Sequence[str], None] = "5defecb7cf98"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMN = "client_id"

# Every table whose ORM model declares ``client_id``. Kept as an explicit list so
# the migration is deterministic and reviewable (rather than importing models and
# reflecting metadata at runtime, which would couple the migration to future model
# edits). Tables already covered by an earlier ARC-05 revision are harmless to
# re-list — the inspector guard turns those into no-ops.
#
# user_id-owner audit (why backfilling client_id from user_id is safe here):
# every table below stamps ``user_id`` with the *owning merchant* (``owner_id`` /
# ``owner_user_id``) at write time — actor identity is isolated elsewhere
# (``audit_logs``, a ``staff_name`` / ``staff_id`` / ``customer_id`` column), and
# NONE of the pure actor/author tables (``audit_logs``, ``login_attempts``,
# ``api_usage``, ``staff_attendance``, ``revoked_tokens``, ``processed_webhook_events``)
# appear in this list. So resolving ``clients.user_id == <table>.user_id`` yields
# the correct tenant. The generic-CRUD tables scope ``user_id`` to the creating
# user, whom ``resolve_tenant_scope`` resolves owner-first — a caller who owns a
# client is never scoped as another tenant's actor — so no cross-tenant
# mis-assignment is reachable. The ``EXISTS`` guard below additionally leaves a
# row NULL rather than guessing when no owning client can be resolved.
_TABLES = [
    "bill_of_materials",
    "branch_catalog_override",
    "branch_promotion_override",
    "branch_tax_rate",
    "branches",
    "campaigns",
    "cash_movements",
    "categories",
    "channel_orders",
    "client_features",
    "combos",
    "customer_consent_events",
    "customer_groups",
    "customer_notes",
    "customers",
    "data_retention_policies",
    "discount_codes",
    "discounts",
    "expenses",
    "floor_zones",
    "gift_card_ledger",
    "gift_cards",
    "happy_hours",
    "kds_tickets",
    "loyalty_points",
    "loyalty_programs",
    "loyalty_transactions",
    "modifier_groups",
    "modifiers",
    "notifications",
    "order_ticket_items",
    "order_tickets",
    "payment_tenders",
    "prep_stations",
    "printers",
    "product_branch_price",
    "product_branch_stock",
    "product_modifier_groups",
    "product_variants",
    "products",
    "promotions",
    "purchase_orders",
    "quotations",
    "receipt_templates",
    "reservations",
    "restaurant_tables",
    "shifts",
    "staff_branch_access",
    "stock_adjustments",
    "stock_count_lines",
    "stock_count_sessions",
    "stock_transfers",
    "store_credit_ledger",
    "subscription_payments",
    "supplier_credit_ledger",
    "suppliers",
    "terminals",
    "transactions",
    "variant_branch_stock",
    "waitlist_entries",
    "webhooks",
    "zatca_credentials",
    "zatca_documents",
]


def _backfill_sql(table: str) -> sa.TextClause:
    """Resolve each row's owning client from its ``user_id`` (lowest-id match)."""
    return sa.text(
        f"""
        UPDATE {table}
           SET {_COLUMN} = (
                SELECT c.id FROM clients c
                 WHERE c.user_id = {table}.user_id
                 ORDER BY c.id ASC
                 LIMIT 1
           )
         WHERE {_COLUMN} IS NULL
           AND EXISTS (
                SELECT 1 FROM clients c WHERE c.user_id = {table}.user_id
           )
        """
    )


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    for table in _TABLES:
        if table not in tables:
            # Table not materialised on this DB (e.g. a vertical never enabled);
            # create_all/its own revision will build it with client_id later.
            continue
        columns = {c["name"] for c in insp.get_columns(table)}
        if _COLUMN not in columns:
            op.add_column(table, sa.Column(_COLUMN, sa.Integer(), nullable=True))
            # Match the ix_<table>_client_id naming used by the per-table ARC-05
            # revisions; guard against a stray pre-existing index.
            existing_ix = {ix["name"] for ix in insp.get_indexes(table)}
            ix_name = f"ix_{table}_{_COLUMN}"
            if ix_name not in existing_ix:
                op.create_index(ix_name, table, [_COLUMN])
            columns.add(_COLUMN)
        # Backfill from the owning client where derivable (table carries user_id).
        if "user_id" in columns:
            op.execute(_backfill_sql(table))


def downgrade() -> None:
    # Non-destructive: earlier revisions / create_all own these columns' baseline
    # existence, so we do not drop them here. (The per-table ARC-05 downgrades still
    # remove the columns they individually introduced.)
    pass
