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


def test_downgrade_to_base_runs_clean(tmp_path):
    """The whole chain reverses: ``upgrade head`` then ``downgrade base`` runs
    every migration's downgrade, in order, without raising.

    This guards against the duplicate-revision / redundant-``drop_index`` /
    index-blocked ``drop_column`` regressions that previously made a full
    round-trip impossible (SQLite ``OperationalError``). Tables built by the
    ``e4f5a6b7c8d9`` create_all squash are intentionally *not* dropped on
    downgrade (that revision documents a no-op downgrade), so this asserts the
    pass completes and that the hand-written pre-squash tables are torn down —
    proof the downgrades actually executed — rather than a fully empty schema.
    """
    db_file = tmp_path / "roundtrip.db"
    sync_url = f"sqlite:///{db_file}"
    cfg = _alembic_cfg(sync_url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")  # must not raise

    engine = create_engine(sync_url)
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    engine.dispose()
    # The original hand-written baseline (368d6a17ebd5) drops these on downgrade;
    # their absence proves the chain's downgrades ran end-to-end.
    for gone in ("transactions", "products", "clients", "agents"):
        assert gone not in tables, f"{gone} should have been dropped on downgrade"


def _skip_alembic_version(obj, name, type_, reflected, compare_to):
    if type_ == "table" and name == "alembic_version":
        return False
    return True


# ---- F-049 (OPS-01): migrations own the schema; create_all is conditional ----


def test_migrations_on_boot_default_is_on_in_prod_off_in_dev(monkeypatch):
    """With no explicit flag, migrations default ON in prod, OFF in dev/CI."""
    from services.migrations import migrations_on_boot_enabled

    monkeypatch.delenv("RUN_MIGRATIONS_ON_BOOT", raising=False)

    monkeypatch.setenv("ENVIRONMENT", "prod")
    assert migrations_on_boot_enabled() is True

    monkeypatch.delenv("ENVIRONMENT", raising=False)  # unset → treated as prod
    assert migrations_on_boot_enabled() is True

    monkeypatch.setenv("ENVIRONMENT", "dev")
    assert migrations_on_boot_enabled() is False


def test_explicit_run_migrations_flag_overrides_environment(monkeypatch):
    """An explicit RUN_MIGRATIONS_ON_BOOT always wins over the env default."""
    from services.migrations import migrations_on_boot_enabled

    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("RUN_MIGRATIONS_ON_BOOT", "true")
    assert migrations_on_boot_enabled() is True

    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("RUN_MIGRATIONS_ON_BOOT", "false")
    assert migrations_on_boot_enabled() is False


async def test_run_migrations_on_boot_returns_false_when_disabled(monkeypatch):
    """Disabled → returns False so the caller falls back to create_all (dev/CI)."""
    from services import migrations as migrations_mod

    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.delenv("RUN_MIGRATIONS_ON_BOOT", raising=False)

    def _boom():  # upgrade must NOT be attempted when disabled
        raise AssertionError("alembic upgrade should not run when migrations are disabled")

    monkeypatch.setattr(migrations_mod, "run_upgrade_head", _boom)
    assert await migrations_mod.run_migrations_on_boot() is False


async def test_initialize_database_skips_create_all_when_migrated(monkeypatch):
    """When migrations own the schema, initialize_database must NOT run create_all."""
    from services import database as database_mod

    calls = {"init_db": 0, "create_tables": 0}

    async def _init_db():
        calls["init_db"] += 1

    async def _create_tables():
        calls["create_tables"] += 1

    monkeypatch.setattr(database_mod.db_manager, "init_db", _init_db)
    monkeypatch.setattr(database_mod.db_manager, "create_tables", _create_tables)
    monkeypatch.delenv("SKIP_INIT_DB", raising=False)

    # Migrations ran → skip create_all (the runtime bootstrap OPS-01 replaces).
    await database_mod.initialize_database(skip_create_all=True)
    assert calls == {"init_db": 1, "create_tables": 0}

    # Dev/CI path (or migrations failed) → create_all still bootstraps the schema.
    await database_mod.initialize_database(skip_create_all=False)
    assert calls == {"init_db": 2, "create_tables": 1}
