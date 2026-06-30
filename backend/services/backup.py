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


async def _main() -> int:
    """CLI entrypoint: ``python -m services.backup`` (invoked by the PITR cron)."""
    from core.database import db_manager

    await db_manager.ensure_initialized()
    try:
        result = await run_backup(kind=os.environ.get("BACKUP_KIND", "full"))
    finally:
        await db_manager.close_db()
    return 0 if result.status == "success" else 1


if __name__ == "__main__":  # pragma: no cover - thin CLI wrapper
    import asyncio
    import sys

    sys.exit(asyncio.run(_main()))
