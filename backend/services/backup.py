"""Postgres backup automation (M10 Ops / #211).

The producer behind the "last backup" health indicator. The PITR cron invokes
``run_backup`` after each scheduled dump; it builds a custom-format ``pg_dump``
archive command from ``DATABASE_URL``, runs it, and — whether the dump succeeds
or fails — heartbeats a row into the ``backup_runs`` ledger that
``GET /api/v1/tenant/master/ops/backups/health`` reads. The cron never has to
speak HTTP or handle a non-zero exit specially: a failed dump still lands a
``failed`` row, so the indicator goes red instead of going silent.

The DR runbook (RPO/RTO targets, region-failover plan, restore-drill procedure)
lives in ``DR_RUNBOOK.md`` at the repo root.
"""
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional, Tuple
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)

# A runner takes the dump argv and the target archive path; it returns
# ``(returncode, stderr)``. Injectable so the orchestration is testable without
# a live Postgres or a real subprocess.
Runner = Callable[[list, str], Tuple[int, str]]


@dataclass
class BackupResult:
    """Outcome of one backup run, mirroring the ledger row it heartbeats."""

    status: str  # success | failed
    kind: str
    size_bytes: Optional[int] = None
    note: Optional[str] = None
    output_path: Optional[str] = None
    finished_at: Optional[datetime] = None


def build_dump_command(database_url: str, out_dir: str, *, label: str) -> Tuple[list, str]:
    """Build a ``pg_dump`` custom-format archive command from a Postgres URL.

    Returns ``(argv, output_path)``. The archive is written with ``-Fc`` (the
    format ``pg_restore`` consumes for point-in-time recovery) to
    ``<out_dir>/pos_backup_<label>.dump``.

    Raises ``ValueError`` for a non-Postgres URL — ``pg_dump`` only speaks to
    Postgres, and the dev SQLite file is not backed up this way.
    """
    parsed = urlparse(database_url)
    scheme = parsed.scheme.split("+", 1)[0].lower()  # postgresql+asyncpg -> postgresql
    if scheme not in ("postgres", "postgresql"):
        raise ValueError(
            f"backup: DATABASE_URL scheme '{parsed.scheme}' is not Postgres; "
            "pg_dump-based backups require a postgres:// database"
        )

    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    user = unquote(parsed.username) if parsed.username else "postgres"
    dbname = (parsed.path or "/").lstrip("/") or "postgres"

    output_path = os.path.join(out_dir, f"pos_backup_{label}.dump")
    argv = [
        "pg_dump",
        "-Fc",
        f"--host={host}",
        f"--port={port}",
        f"--username={user}",
        f"--dbname={dbname}",
        f"--file={output_path}",
    ]
    return argv, output_path


def build_restore_command(
    database_url: str, archive_path: str, *, target_db: str
) -> Tuple[list, str]:
    """Build a ``pg_restore`` command that drills ``archive_path`` into a scratch DB.

    Returns ``(argv, target_db)``. The drill restores into ``target_db`` — a
    throwaway database on the same server — never the live database named in
    ``database_url``; the caller creates and drops that scratch DB around the
    drill. ``--no-owner`` lets the restore succeed even when the drill role does
    not match the dump's original owners.

    Raises ``ValueError`` for a non-Postgres URL, mirroring
    :func:`build_dump_command` — ``pg_restore`` only speaks to Postgres.
    """
    parsed = urlparse(database_url)
    scheme = parsed.scheme.split("+", 1)[0].lower()  # postgresql+asyncpg -> postgresql
    if scheme not in ("postgres", "postgresql"):
        raise ValueError(
            f"restore drill: DATABASE_URL scheme '{parsed.scheme}' is not Postgres; "
            "pg_restore-based drills require a postgres:// database"
        )

    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    user = unquote(parsed.username) if parsed.username else "postgres"

    argv = [
        "pg_restore",
        "--no-owner",
        f"--host={host}",
        f"--port={port}",
        f"--username={user}",
        f"--dbname={target_db}",
        archive_path,
    ]
    return argv, target_db


def _subprocess_runner(argv: list, out_path: str) -> Tuple[int, str]:
    """Default runner: invoke ``pg_dump`` as a subprocess.

    The password is passed via ``PGPASSWORD`` in the child environment so it
    never appears in the process's argv / logs.
    """
    import subprocess

    proc = subprocess.run(argv, capture_output=True, text=True)
    return proc.returncode, proc.stderr or ""


async def _record_run(result: BackupResult) -> None:
    """Append the run to the ``backup_runs`` ledger in a fresh session."""
    from core.database import db_manager
    from models.backup_runs import Backup_runs

    async with db_manager.async_session_maker() as db:
        db.add(
            Backup_runs(
                kind=result.kind,
                status=result.status,
                size_bytes=result.size_bytes,
                note=result.note,
                finished_at=result.finished_at,
            )
        )
        await db.commit()


async def run_backup(
    *,
    database_url: Optional[str] = None,
    out_dir: Optional[str] = None,
    kind: str = "full",
    label: Optional[str] = None,
    runner: Optional[Runner] = None,
    record: bool = True,
) -> BackupResult:
    """Run one backup and heartbeat the ledger; never raises on a dump failure.

    ``database_url``/``out_dir`` default to ``DATABASE_URL`` / ``BACKUP_DIR``
    (falling back to ``./backups``). ``label`` defaults to a UTC timestamp so
    successive runs never overwrite each other. A non-zero dump exit records a
    ``failed`` row rather than crashing the cron job.
    """
    database_url = database_url or os.environ.get("DATABASE_URL", "")
    out_dir = out_dir or os.environ.get("BACKUP_DIR", "./backups")
    runner = runner or _subprocess_runner
    finished_at = datetime.now(timezone.utc)
    if label is None:
        label = finished_at.strftime("%Y%m%d_%H%M%S")

    os.makedirs(out_dir, exist_ok=True)
    argv, output_path = build_dump_command(database_url, out_dir, label=label)

    try:
        returncode, stderr = runner(argv, output_path)
    except Exception as exc:  # the runner itself blew up (e.g. pg_dump not found)
        returncode, stderr = 1, str(exc)

    if returncode == 0:
        size_bytes = os.path.getsize(output_path) if os.path.isfile(output_path) else None
        result = BackupResult(
            status="success",
            kind=kind,
            size_bytes=size_bytes,
            output_path=output_path,
            finished_at=finished_at,
        )
        logger.info("backup: %s archive written to %s (%s bytes)", kind, output_path, size_bytes)
    else:
        result = BackupResult(
            status="failed",
            kind=kind,
            note=(stderr or "pg_dump failed").strip()[:500],
            output_path=output_path,
            finished_at=finished_at,
        )
        logger.error("backup: %s dump failed: %s", kind, result.note)

    if record:
        try:
            await _record_run(result)
        except Exception:  # heartbeating must not mask the backup outcome
            logger.exception("backup: failed to record run in the ledger")

    return result


async def run_restore_drill(
    *,
    database_url: Optional[str] = None,
    archive_path: str,
    target_db: Optional[str] = None,
    runner: Optional[Runner] = None,
    record: bool = True,
) -> BackupResult:
    """Drill ``archive_path`` into a scratch DB and heartbeat the ledger.

    Proves a backup is restorable — the half of disaster recovery a green
    "last backup" dot does not cover. ``pg_restore`` runs into ``target_db``
    (default: the live DB name + ``_drill``), and — whether it succeeds or
    fails — a ``restore_drill`` row lands in the ``backup_runs`` ledger so the
    health endpoint can show "last restore drill: passed/failed". A failed
    drill records a ``failed`` row rather than raising, exactly like
    :func:`run_backup`, so the quarterly drill cron never crashes on a broken
    archive — it just goes red.
    """
    database_url = database_url or os.environ.get("DATABASE_URL", "")
    runner = runner or _subprocess_runner
    finished_at = datetime.now(timezone.utc)

    if target_db is None:
        live_db = (urlparse(database_url).path or "/").lstrip("/") or "postgres"
        target_db = f"{live_db}_drill"

    argv, _ = build_restore_command(database_url, archive_path, target_db=target_db)

    try:
        returncode, stderr = runner(argv, archive_path)
    except Exception as exc:  # pg_restore not found, scratch DB unreachable, etc.
        returncode, stderr = 1, str(exc)

    if returncode == 0:
        result = BackupResult(
            status="success",
            kind="restore_drill",
            note=f"restored into {target_db}",
            finished_at=finished_at,
        )
        logger.info("restore drill: archive %s restored into %s", archive_path, target_db)
    else:
        result = BackupResult(
            status="failed",
            kind="restore_drill",
            note=(stderr or "pg_restore failed").strip()[:500],
            finished_at=finished_at,
        )
        logger.error("restore drill: %s failed to restore: %s", archive_path, result.note)

    if record:
        try:
            await _record_run(result)
        except Exception:  # heartbeating must not mask the drill outcome
            logger.exception("restore drill: failed to record run in the ledger")

    return result


async def _main() -> int:
    """CLI entrypoint: ``python -m services.backup`` (invoked by the PITR cron)."""
    from core.database import db_manager

    await db_manager.ensure_initialized()
    try:
        result = await run_backup(kind=os.environ.get("BACKUP_KIND", "full"))
    finally:
        await db_manager.close_db()
    return 0 if result.status == "success" else 1


async def _drill_main(archive_path: str) -> int:
    """CLI entrypoint: ``python -m services.backup --drill <archive>`` (quarterly drill)."""
    from core.database import db_manager

    await db_manager.ensure_initialized()
    try:
        result = await run_restore_drill(
            archive_path=archive_path,
            target_db=os.environ.get("RESTORE_DRILL_DB"),
        )
    finally:
        await db_manager.close_db()
    return 0 if result.status == "success" else 1


if __name__ == "__main__":  # pragma: no cover - thin CLI wrapper
    import asyncio
    import sys

    if len(sys.argv) >= 3 and sys.argv[1] == "--drill":
        sys.exit(asyncio.run(_drill_main(sys.argv[2])))
    sys.exit(asyncio.run(_main()))
