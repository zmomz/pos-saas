from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, BigInteger


class Backup_runs(Base):
    """Append-only ledger of database backup runs (M10 Ops / #211).

    One row per backup attempt, heartbeated by the Postgres PITR cron via
    ``POST /api/v1/tenant/master/ops/backups`` after each (full / incremental /
    wal) run finishes. The master-only ``/ops/backups/health`` endpoint reads the
    latest rows to turn this ledger into a "last backup" indicator — fresh /
    stale / failing / missing — against the documented RPO/RTO targets.

    The backup automation, DR runbook, and live restore drill are tracked on the
    parent issue; this ledger is the observability surface they report into.
    """

    __tablename__ = "backup_runs"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    kind = Column(String, nullable=False)  # full | incremental | wal
    status = Column(String, nullable=False)  # success | failed
    size_bytes = Column(BigInteger, nullable=True)
    note = Column(String, nullable=True)
    # When the backup actually completed (the instant that bounds the RPO window).
    # Defaults to insertion time when the cron does not supply it.
    finished_at = Column(DateTime(timezone=True), default=datetime.now, index=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now, index=True)
