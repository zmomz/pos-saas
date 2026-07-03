"""ARC-05 sweep (``c11d5f1xed01``) — heals a drifted, already-baselined DB.

The consolidated ``client_id`` backfill sweep exists for one prod-only failure
mode (OPS-01): a DB that was baselined via ``create_all`` *before* a model grew
its ``client_id`` column never receives that column — ``create_all`` skips an
existing table and emits no ``ALTER``. The endpoint then 500s with
``no such column: <table>.client_id``.

These tests reconstruct that exact drift on ``expenses`` (a representative
``user_id``-owned table): they upgrade to the revision *before* the sweep, DROP
the ``client_id`` column to simulate the pre-drift shape, seed rows, then run the
sweep and assert it (a) re-adds the column + index and (b) backfills
``client_id`` from the owning ``clients`` row — while leaving a row whose owner
is unknown NULL (the ``EXISTS`` guard can never mis-assign a tenant) and a row
that already carried a ``client_id`` untouched.
"""
import os

from sqlalchemy import create_engine, inspect, text

from alembic import command
from alembic.config import Config

SWEEP = "c11d5f1xed01"
PRIOR = "5defecb7cf98"  # the sweep's down_revision


def _alembic_cfg(db_url: str) -> Config:
    ini = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic.ini"
    )
    cfg = Config(ini)
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _seed_client(conn, user_id: str) -> int:
    conn.execute(
        text(
            "INSERT INTO clients (user_id, agent_id, business_name, email) "
            "VALUES (:u, 1, :n, :e)"
        ),
        {"u": user_id, "n": f"biz-{user_id}", "e": f"{user_id}@x.co"},
    )
    return conn.execute(
        text("SELECT id FROM clients WHERE user_id = :u"), {"u": user_id}
    ).scalar_one()


def test_sweep_adds_column_index_and_backfills_from_owner(tmp_path):
    db_file = tmp_path / "drift.db"
    sync_url = f"sqlite:///{db_file}"
    cfg = _alembic_cfg(sync_url)

    # 1. Build the schema as it stood at the sweep's parent revision.
    command.upgrade(cfg, PRIOR)

    engine = create_engine(sync_url)
    # 2. Recreate the drift: an already-baselined DB missing expenses.client_id.
    #    SQLite refuses to DROP an indexed column, so drop its index first.
    with engine.begin() as conn:
        owner = _seed_client(conn, "owner-1")
        other = _seed_client(conn, "owner-2")
        conn.execute(text("DROP INDEX IF EXISTS ix_expenses_client_id"))
        conn.execute(text("ALTER TABLE expenses DROP COLUMN client_id"))
        # Owned by a user that HAS a client — must backfill to that client.
        conn.execute(
            text("INSERT INTO expenses (user_id, category, amount) VALUES ('owner-1','Rent',100.0)")
        )
        # Owned by a user with NO client row — must stay NULL (EXISTS guard).
        conn.execute(
            text("INSERT INTO expenses (user_id, category, amount) VALUES ('ghost','Misc',9.0)")
        )

    insp = inspect(engine)
    assert "client_id" not in {c["name"] for c in insp.get_columns("expenses")}, (
        "drift setup failed: client_id should be absent before the sweep"
    )
    engine.dispose()

    # 3. Run the sweep.
    command.upgrade(cfg, SWEEP)

    # 4a. Column + index are healed.
    engine = create_engine(sync_url)
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("expenses")}
    assert "client_id" in cols
    assert "ix_expenses_client_id" in {i["name"] for i in insp.get_indexes("expenses")}

    # 4b. Backfilled from the owning client; unknown-owner row stays NULL.
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT user_id, client_id FROM expenses ORDER BY user_id")
        ).all()
    engine.dispose()

    by_user = {u: c for u, c in rows}
    assert by_user["owner-1"] == owner, "row must backfill to its owning client"
    assert by_user["ghost"] is None, "no client owner → must stay NULL (never mis-assigned)"
    assert other != owner  # sanity: the two clients are distinct


def test_sweep_is_idempotent_and_preserves_existing_client_id(tmp_path):
    """A second run is a no-op, and a row that already had a client_id is untouched."""
    db_file = tmp_path / "idem.db"
    sync_url = f"sqlite:///{db_file}"
    cfg = _alembic_cfg(sync_url)

    # Fresh upgrade to head: client_id already present (create_all baseline), so
    # the sweep is a pure no-op here.
    command.upgrade(cfg, "head")

    engine = create_engine(sync_url)
    with engine.begin() as conn:
        owner = _seed_client(conn, "owner-1")
        # A row that already carries a (deliberately "wrong-but-explicit") client_id
        # must NOT be rewritten — the backfill only fills WHERE client_id IS NULL.
        conn.execute(
            text(
                "INSERT INTO expenses (user_id, client_id, category, amount) "
                "VALUES ('owner-1', 4242, 'Rent', 5.0)"
            )
        )
        # A NULL row that should get backfilled on the sweep re-run.
        conn.execute(
            text("INSERT INTO expenses (user_id, category, amount) VALUES ('owner-1', 'Supplies', 7.0)")
        )
    engine.dispose()

    # Re-run the sweep in isolation (down one then back up), exercising its body
    # against a live DB with data.
    command.downgrade(cfg, PRIOR)  # sweep downgrade is a no-op (non-destructive)
    command.upgrade(cfg, SWEEP)

    engine = create_engine(sync_url)
    with engine.connect() as conn:
        explicit = conn.execute(
            text("SELECT client_id FROM expenses WHERE amount = 5.0")
        ).scalar_one()
        filled = conn.execute(
            text("SELECT client_id FROM expenses WHERE amount = 7.0")
        ).scalar_one()
    engine.dispose()

    assert explicit == 4242, "an explicit client_id must be preserved, never overwritten"
    assert filled == owner, "a NULL client_id must be backfilled from the owner"
