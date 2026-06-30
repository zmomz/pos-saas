# Disaster Recovery Runbook (M10 Ops · #211)

This runbook is the documented recovery procedure that the backup **automation**
(`backend/services/backup.py`) and the master **health indicator**
(`GET /api/v1/tenant/master/ops/backups/health`) report against. Keep it current:
the recovery targets below are the same constants the indicator measures freshness
against (`BACKUP_RPO_TARGET_SECONDS` / `BACKUP_RTO_TARGET_SECONDS` in
`backend/routers/tenant.py`).

## Recovery targets

| Target | Value | Meaning |
| ------ | ----- | ------- |
| **RPO** (Recovery Point Objective) | **24h** | Maximum acceptable data loss. A successful backup must have landed within the last 24 hours, or the health indicator goes `stale`. |
| **RTO** (Recovery Time Objective)  | **4h**  | Maximum acceptable time to restore service after a declared disaster. |

## Backup automation (Postgres PITR)

The PITR cron runs the backup routine after each scheduled window:

```sh
# Daily full archive (custom-format, the format pg_restore consumes for PITR).
cd backend && DATABASE_URL=postgresql://… BACKUP_DIR=/var/backups/pos \
  python -m services.backup
```

Each run heartbeats the `backup_runs` ledger (a `success` row with the archive
size, or a `failed` row with the `pg_dump` stderr) — so a silent cron failure
still turns the indicator red instead of going dark. Ship the archives to
off-host / cross-region object storage with versioning + lifecycle retention.

**Verify the indicator after wiring the cron:**

```sh
curl -H "Authorization: Bearer <master-token>" \
  https://<host>/api/v1/tenant/master/ops/backups/health
# => {"status":"ok","age_seconds":…,"rpo_target_seconds":86400,"rto_target_seconds":14400,…}
```

The "last backup" indicator surfaces this payload: `ok` / `stale` / `failing` /
`missing`.

## Region failover plan

1. Declare the disaster and freeze writes to the primary region.
2. Promote the cross-region Postgres replica (or restore the latest off-site
   archive — see below) to primary.
3. Repoint the application's `DATABASE_URL` / connection string at the promoted
   instance and roll the app tier in the failover region.
4. Update DNS / load-balancer to the failover region; confirm `/health` and the
   backup health indicator are green.
5. Re-establish replication back to the recovered primary before failing back.

## Offline-queue-drain validation

POS terminals queue sales while offline and drain them on reconnect. After any
failover or restore, **before reopening trade**:

1. Bring one terminal online against the recovered backend.
2. Confirm its queued offline sales drain and reconcile (no duplicate invoice
   numbers, ledger balances match).
3. Only then release the remaining terminals.

This guards against the failover losing in-flight offline transactions.

## Restore drill (run quarterly)

A restore is only real once it has been *practised*. Quarterly:

1. Provision a throwaway Postgres instance.
2. Restore the latest off-site archive:
   ```sh
   pg_restore --clean --if-exists --dbname=postgresql://…/posdb_drill pos_backup_<label>.dump
   ```
3. Boot the app against the restored database; smoke-test login, a sale, and a
   report.
4. **Time it** end-to-end and confirm it is within the **4h RTO**; confirm the
   restored data is within the **24h RPO**.
5. Record the drill date, measured restore time, and any gaps in the table below.

### Restore-drill log

| Date | Archive label | Measured restore time | Within RTO? | Notes |
| ---- | ------------- | --------------------- | ----------- | ----- |
| _TBD_ | _TBD_ | _TBD_ | _TBD_ | First live drill pending. |
