"""Issue #211 — Postgres backup automation (M10 Ops).

The "last backup" health indicator (test_issue211_backup_health.py) reads a
ledger of backup runs. This slice is the *producer*: a self-contained backup
routine the PITR cron invokes after each run. It builds a ``pg_dump`` archive
command from ``DATABASE_URL`` and, whether the dump succeeds or fails,
heartbeats a row into the same ``backup_runs`` ledger — so the indicator goes
green on success and red on failure without the cron needing to speak HTTP.

Tested through the public ``services.backup`` interface with an injected runner
(no live Postgres or subprocess); the end-to-end checks confirm a recorded run
surfaces on the master health endpoint.
"""
import os

from conftest import auth_headers, make_master_account

from services import backup

HEALTH = "/api/v1/tenant/master/ops/backups/health"


# ---------- build_dump_command: Postgres archive invocation ----------

def test_build_dump_command_for_postgres(tmp_path):
    argv, out_path = backup.build_dump_command(
        "postgresql://poses:secret@db.internal:6432/posdb",
        str(tmp_path),
        label="20260630_000000",
    )

    # A custom-format (-Fc) archive — the format `pg_restore` consumes for PITR.
    assert argv[0] == "pg_dump"
    assert "-Fc" in argv
    assert "--host=db.internal" in argv
    assert "--port=6432" in argv
    assert "--username=poses" in argv
    assert "--dbname=posdb" in argv
    # Output lands at the returned path, and the command writes there (-f).
    assert out_path == os.path.join(str(tmp_path), "pos_backup_20260630_000000.dump")
    assert f"--file={out_path}" in argv


def test_build_dump_command_rejects_non_postgres(tmp_path):
    # PITR/pg_dump is Postgres-only; the dev SQLite file is not backed up this way.
    try:
        backup.build_dump_command("sqlite:///./app.db", str(tmp_path), label="x")
    except ValueError as exc:
        assert "postgres" in str(exc).lower()
    else:
        raise AssertionError("expected ValueError for a non-Postgres DATABASE_URL")


# ---------- run_backup: success heartbeats the ledger (green indicator) ----------

async def test_run_backup_records_success_and_health_reflects_it(client, tmp_path):
    _, master_token = await make_master_account(client)

    def fake_runner(argv, out_path):
        # Simulate pg_dump writing a real archive.
        with open(out_path, "wb") as fh:
            fh.write(b"PGDMP" + b"0" * 100)
        return 0, ""

    result = await backup.run_backup(
        database_url="postgresql://u:p@h:5432/posdb",
        out_dir=str(tmp_path),
        label="20260630_010101",
        runner=fake_runner,
    )

    assert result.status == "success"
    assert result.size_bytes == 105
    assert os.path.isfile(result.output_path)

    body = (await client.get(HEALTH, headers=auth_headers(master_token))).json()
    assert body["status"] == "ok"
    assert body["total_runs"] == 1
    assert body["last_run_status"] == "success"


# ---------- run_backup: failure heartbeats without raising (red indicator) ----------

async def test_run_backup_records_failure_without_raising(client, tmp_path):
    _, master_token = await make_master_account(client)

    def failing_runner(argv, out_path):
        return 1, "pg_dump: error: connection to server failed"

    result = await backup.run_backup(
        database_url="postgresql://u:p@h:5432/posdb",
        out_dir=str(tmp_path),
        label="20260630_020202",
        runner=failing_runner,
    )

    # Cron-friendly: it records the failure rather than crashing the cron job.
    assert result.status == "failed"
    assert result.note and "connection to server failed" in result.note

    body = (await client.get(HEALTH, headers=auth_headers(master_token))).json()
    assert body["status"] == "failing"
    assert body["last_run_status"] == "failed"
