"""ISSUE-225 (M10 Admin) — job/queue monitor (admin-console slice).

The third end-to-end slice of the operator admin console (after maintenance mode
and the feature-flag console): a platform master can read a **read-only monitor**
of the background-job queue from an admin endpoint, and the state is real, never
fabricated:

- the master reads the live job registry (every declared background job) plus the
  active queue backend and its health;
- under the default ``memory`` backend jobs run inline, so there is no durable
  queue to fall behind on (``queued`` is 0) and nothing to be "down"
  (``healthy`` True);
- when the ``redis`` backend is selected but the broker is unreachable, the
  monitor reports ``healthy`` False rather than inventing an up-state;
- a non-master tenant cannot read the platform job monitor (403).
"""
import pytest

from conftest import auth_headers, make_client_account, make_master_account

# The background jobs the platform declares (services/jobs.py). The monitor must
# surface these from the LIVE registry, not a hand-maintained list.
KNOWN_JOBS = {
    "webhook.deliver",
    "zatca.reconcile",
    "report.materialize",
    "notification.dispatch",
    "export.generate",
}


async def _read_jobs(client, headers):
    return await client.get("/api/v1/admin/jobs", headers=headers)


@pytest.mark.asyncio
async def test_master_reads_job_monitor_with_live_registry(client):
    """The master reads the monitor: memory backend, healthy, every declared job listed."""
    _user, token = await make_master_account(client)
    headers = auth_headers(token)

    resp = await _read_jobs(client, headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # The default CI/dev backend runs jobs inline — no durable queue, always up.
    assert body["backend"] == "memory"
    assert body["healthy"] is True
    assert body["queued"] == 0

    # Every declared job is surfaced, from the live registry (not fabricated), sorted.
    jobs = body["registered_jobs"]
    assert KNOWN_JOBS.issubset(set(jobs))
    assert jobs == sorted(jobs)


@pytest.mark.asyncio
async def test_non_master_cannot_read_job_monitor(client):
    """A tenant operator has no business reading the platform job monitor (403)."""
    _user, token, _client_id = await make_client_account(client)
    headers = auth_headers(token)

    assert (await _read_jobs(client, headers)).status_code == 403


@pytest.mark.asyncio
async def test_redis_backend_reports_unhealthy_when_broker_unreachable(monkeypatch):
    """Selecting redis with no reachable broker reports healthy=False — no invented up-state."""
    from core.config import settings
    from services import job_queue

    monkeypatch.setattr(settings, "job_queue_backend", "redis", raising=False)
    monkeypatch.setattr(settings, "redis_url", "", raising=False)

    stats = await job_queue.queue_stats()

    assert stats["backend"] == "redis"
    assert stats["healthy"] is False
    assert stats["queued"] == 0
    # The registry is still surfaced regardless of broker state.
    assert KNOWN_JOBS.issubset(set(stats["registered_jobs"]))
