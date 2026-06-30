"""Issue #211 — surface a "last backup" health indicator (M10 Ops).

The agent-runnable slice of the backup/restore epic: an append-only ledger of
backup runs (heartbeated by the Postgres PITR cron) plus a master-only health
endpoint that turns the latest run into an operable indicator — fresh / stale /
failing / missing — measured against the documented RPO/RTO targets.

The PITR automation itself, the DR runbook, and the live restore drill are real
ops work tracked on the parent issue; this slice gives the platform the
observability surface those depend on.

All endpoints are master-only (SEC-02): the platform operator owns DR posture,
an agent/client gets 403.
"""
from datetime import datetime, timedelta, timezone

from conftest import auth_headers, make_agent_account, make_master_account

RECORD = "/api/v1/tenant/master/ops/backups"
HEALTH = "/api/v1/tenant/master/ops/backups/health"


async def _record(client, token, **body):
    return await client.post(RECORD, headers=auth_headers(token), json=body)


# ---------- health: missing (no runs ever) ----------

async def test_health_missing_when_no_runs(client):
    _, master_token = await make_master_account(client)

    resp = await client.get(HEALTH, headers=auth_headers(master_token))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "missing"
    assert body["last_success_at"] is None
    assert body["total_runs"] == 0
    # RPO/RTO targets are documented and surfaced so the indicator is operable.
    assert body["rpo_target_seconds"] > 0
    assert body["rto_target_seconds"] > 0


# ---------- master-only gating (SEC-02) ----------

async def test_health_forbidden_for_non_master(client):
    _, agent_token, _ = await make_agent_account(client)

    resp = await client.get(HEALTH, headers=auth_headers(agent_token))

    assert resp.status_code == 403


async def test_record_forbidden_for_non_master(client):
    _, agent_token, _ = await make_agent_account(client)

    resp = await _record(client, agent_token, status="success", kind="full")

    assert resp.status_code == 403


# ---------- health: ok (a fresh successful backup landed) ----------

async def test_health_ok_after_fresh_success(client):
    _, master_token = await make_master_account(client)

    rec = await _record(client, master_token, status="success", kind="full", size_bytes=1234)
    assert rec.status_code == 201, rec.text

    body = (await client.get(HEALTH, headers=auth_headers(master_token))).json()
    assert body["status"] == "ok"
    assert body["last_success_at"] is not None
    assert body["total_runs"] == 1
    assert body["age_seconds"] is not None and body["age_seconds"] >= 0
    assert body["age_seconds"] <= body["rpo_target_seconds"]


# ---------- health: stale (newest success is older than the RPO target) ----------

async def test_health_stale_when_last_success_beyond_rpo(client):
    _, master_token = await make_master_account(client)

    # A successful backup that finished two days ago — past the 24h RPO window.
    old = datetime.now(timezone.utc) - timedelta(days=2)
    rec = await _record(
        client, master_token, status="success", kind="full",
        finished_at=old.isoformat(),
    )
    assert rec.status_code == 201, rec.text

    body = (await client.get(HEALTH, headers=auth_headers(master_token))).json()
    assert body["status"] == "stale"
    assert body["last_success_at"] is not None
    assert body["age_seconds"] > body["rpo_target_seconds"]


# ---------- health: failing (the most recent run failed) ----------

async def test_health_failing_when_latest_run_failed(client):
    _, master_token = await make_master_account(client)

    # A good backup, then a more recent failure — the indicator must go red.
    earlier = datetime.now(timezone.utc) - timedelta(hours=2)
    later = datetime.now(timezone.utc) - timedelta(minutes=5)
    await _record(
        client, master_token, status="success", kind="full",
        finished_at=earlier.isoformat(),
    )
    await _record(
        client, master_token, status="failed", kind="full",
        finished_at=later.isoformat(), note="pg_basebackup exited 1",
    )

    body = (await client.get(HEALTH, headers=auth_headers(master_token))).json()
    assert body["status"] == "failing"
    assert body["last_run_status"] == "failed"
    # The last *successful* backup is still surfaced for context.
    assert body["last_success_at"] is not None
    assert body["total_runs"] == 2
