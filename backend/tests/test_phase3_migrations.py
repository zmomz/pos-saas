"""Phase 3 (deferred): Alembic migrations-on-boot.

Proves that ``alembic upgrade head`` on a fresh database builds the *current*
model schema (including the columns/tables Phases 2–6 added at runtime) and that
no autogenerate diff remains afterwards — i.e. the migration chain is in sync
with the ORM models, which is the precondition for enabling migrations on boot.
"""
import os

import pytest
from sqlalchemy import create_engine, inspect

from alembic import command
from alembic.config import Config
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext

from core.database import Base


def _alembic_cfg(db_url: str) -> Config:
    ini = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic.ini")
    cfg = Config(ini)
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_upgrade_head_builds_current_schema(tmp_path):
    db_file = tmp_path / "mig.db"
    sync_url = f"sqlite:///{db_file}"
    cfg = _alembic_cfg(sync_url)

    command.upgrade(cfg, "head")

    engine = create_engine(sync_url)
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    # Tables that only ever existed via runtime create_all / later phases.
    assert "transactions" in tables
    assert "revoked_tokens" in tables
    assert "subscription_payments" in tables
    assert "branches" in tables
    assert "product_branch_stock" in tables

    # Columns Phases 2/4/6 added at runtime must be present after upgrade head.
    tx_cols = {c["name"] for c in insp.get_columns("transactions")}
    assert {"branch_id", "shift_id", "offline_id"} <= tx_cols
    engine.dispose()


def test_autogenerate_diff_is_empty_after_upgrade(tmp_path):
    db_file = tmp_path / "diff.db"
    sync_url = f"sqlite:///{db_file}"
    cfg = _alembic_cfg(sync_url)
    command.upgrade(cfg, "head")

    engine = create_engine(sync_url)
    with engine.connect() as conn:
        ctx = MigrationContext.configure(
            conn, opts={"compare_type": True, "include_object": _skip_alembic_version}
        )
        diff = compare_metadata(ctx, Base.metadata)
    engine.dispose()

    assert diff == [], f"Models drifted from migrations: {diff}"


def _skip_alembic_version(obj, name, type_, reflected, compare_to):
    if type_ == "table" and name == "alembic_version":
        return False
    return True
