"""Issue #211 — automated restore drill (M10 Ops).

A backup you have never restored is a backup you do not have. The DR runbook
documents the restore-drill *procedure*; this slice makes it *executable*: a
self-contained routine the quarterly drill cron invokes to prove the newest
``pg_dump`` archive is actually restorable. It runs ``pg_restore`` into a
throwaway scratch database and — pass or fail — heartbeats a ``restore_drill``
row into the same ``backup_runs`` ledger the "last backup" indicator reads, so
the master health endpoint can also surface "last restore drill: passed 3 days
ago" against the documented RTO target.

Tested through the public ``services.backup`` interface with an injected runner
(no live Postgres or subprocess); the end-to-end checks confirm a recorded
drill surfaces on the master health endpoint.
"""
import os

from conftest import auth_headers, make_master_account

from services import backup

HEALTH = "/api/v1/tenant/master/ops/backups/health"


# ---------- build_restore_command: pg_restore into a scratch database ----------

def test_build_restore_command_for_postgres(tmp_path):
    archive = os.path.join(str(tmp_path), "pos_backup_20260630_000000.dump")
    argv, scratch_db = backup.build_restore_command(
        "postgresql://poses:secret@db.internal:6432/posdb",
        archive,
        target_db="posdb_drill",
    )

    # pg_restore consumes the -Fc archive run_backup writes.
    assert argv[0] == "pg_restore"
    assert "--host=db.internal" in argv
    assert "--port=6432" in argv
    assert "--username=poses" in argv
    # It restores into the throwaway scratch DB, never the live database.
    assert scratch_db == "posdb_drill"
    assert "--dbname=posdb_drill" in argv
    # The drill must not abort the cron on the first benign restore notice.
    assert archive in argv


def test_build_restore_command_rejects_non_postgres(tmp_path):
    # pg_restore is Postgres-only, mirroring build_dump_command.
    try:
        backup.build_restore_command("sqlite:///./app.db", "x.dump", target_db="d")
    except ValueError as exc:
        assert "postgres" in str(exc).lower()
    else:
        raise AssertionError("expected ValueError for a non-Postgres DATABASE_URL")


# ---------- run_restore_drill: a passing drill heartbeats the ledger ----------

async def test_run_restore_drill_records_success_and_health_reflects_it(client, tmp_path):
    _, master_token = await make_master_account(client)
    archive = os.path.join(str(tmp_path), "pos_backup_20260630_010101.dump")
    with open(archive, "wb") as fh:
        fh.write(b"PGDMP" + b"0" * 100)

    def fake_runner(argv, _out):
        return 0, ""  # pg_restore into the scratch DB succeeded

    result = await backup.run_restore_drill(
        database_url="postgresql://u:p@h:5432/posdb",
        archive_path=archive,
        target_db="posdb_drill",
        runner=fake_runner,
    )

    assert result.status == "success"
    assert result.kind == "restore_drill"

    body = (await client.get(HEALTH, headers=auth_headers(master_token))).json()
    # The drill row is a distinct kind: it must surface as a *restore* signal,
    # not be mistaken for a fresh backup landing.
    assert body["last_drill_status"] == "success"
    assert body["last_drill_at"] is not None


# ---------- run_restore_drill: a failing drill records without raising ----------

async def test_run_restore_drill_records_failure_without_raising(client, tmp_path):
    _, master_token = await make_master_account(client)
    archive = os.path.join(str(tmp_path), "pos_backup_20260630_020202.dump")
    with open(archive, "wb") as fh:
        fh.write(b"PGDMP")

    def failing_runner(argv, _out):
        return 1, "pg_restore: error: could not execute query: relation already exists"

    result = await backup.run_restore_drill(
        database_url="postgresql://u:p@h:5432/posdb",
        archive_path=archive,
        target_db="posdb_drill",
        runner=failing_runner,
    )

    # Cron-friendly: a broken backup turns the drill red rather than crashing it.
    assert result.status == "failed"
    assert result.note and "relation already exists" in result.note

    body = (await client.get(HEALTH, headers=auth_headers(master_token))).json()
    assert body["last_drill_status"] == "failed"
