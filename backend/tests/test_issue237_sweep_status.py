"""Issue #237 — surface the omnichannel stuck-claim sweep status in the UI.

The bounded crash-recovery sweep (``services.aggregator.recover_stuck_aggregator_claims``,
REV-05) re-opens channel-order claims whose settler died mid-flight (stranded at
``settling``). It runs unattended inside the billing scheduler tick — but operators had
no way to see it was keeping up. These tests cover the read surface the omnichannel UI
consumes: ``GET /api/v1/omnichannel/sweep-status`` reports live stuck-claim health
(owner-scoped) plus the last unattended run (when + how many it recovered).
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from conftest import auth_headers, make_client_account, register_user
from core.database import db_manager
from models.channel_orders import Channel_orders
from services.aggregator import record_omnichannel_sweep_run


async def _seed_claim(user_id, client_id, *, status, settling_at=None, external_id=None):
    async with db_manager.async_session_maker() as db:
        db.add(
            Channel_orders(
                user_id=user_id,
                client_id=client_id,
                provider="deliverect",
                external_order_id=external_id or f"EXT-{uuid.uuid4().hex[:8]}",
                status=status,
                settling_at=settling_at,
                total_amount=40.0,
                currency="SAR",
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_sweep_status_healthy_when_no_stuck_claims(client):
    """An imported order and a *fresh* settling lock (a settle genuinely in flight)
    are not stuck — the sweep is healthy."""
    user, token, client_id = await make_client_account(client)
    await _seed_claim(user["id"], client_id, status="imported")
    await _seed_claim(
        user["id"], client_id, status="settling", settling_at=datetime.now(timezone.utc)
    )

    resp = await client.get("/api/v1/omnichannel/sweep-status", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["stuck_count"] == 0
    assert body["healthy"] is True
    assert body["oldest_stuck_age_seconds"] is None


@pytest.mark.asyncio
async def test_sweep_status_flags_stuck_settling_claim(client):
    """A claim stranded at ``settling`` past the recovery threshold is flagged stuck —
    the sweep has not recovered it yet, so the UI shows un-healthy."""
    user, token, client_id = await make_client_account(client)
    stale = datetime.now(timezone.utc) - timedelta(seconds=3600)
    await _seed_claim(user["id"], client_id, status="settling", settling_at=stale)

    resp = await client.get("/api/v1/omnichannel/sweep-status", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["stuck_count"] == 1
    assert body["healthy"] is False
    assert body["oldest_stuck_age_seconds"] >= 600
    assert body["threshold_seconds"] == 600


@pytest.mark.asyncio
async def test_sweep_status_reports_last_run(client):
    """The persisted last unattended run (ran_at + recovered count) is surfaced."""
    user, token, client_id = await make_client_account(client)
    async with db_manager.async_session_maker() as db:
        await record_omnichannel_sweep_run(
            db, reopened=3, now=datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
        )

    resp = await client.get("/api/v1/omnichannel/sweep-status", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["last_reopened"] == 3
    assert body["last_run_at"].startswith("2026-06-30T12:00")


@pytest.mark.asyncio
async def test_sweep_status_is_owner_scoped(client):
    """Client B never sees client A's stuck claims (SEC-02)."""
    user_a, _token_a, client_a = await make_client_account(client)
    _user_b, token_b, _client_b = await make_client_account(client)
    stale = datetime.now(timezone.utc) - timedelta(seconds=3600)
    await _seed_claim(user_a["id"], client_a, status="settling", settling_at=stale)

    resp_b = await client.get("/api/v1/omnichannel/sweep-status", headers=auth_headers(token_b))
    assert resp_b.status_code == 200, resp_b.text
    assert resp_b.json()["stuck_count"] == 0


@pytest.mark.asyncio
async def test_sweep_status_requires_client_tenancy(client):
    """A non-client account (no tenancy) is rejected 403 — omnichannel is client-scoped."""
    _user, token, _ = await register_user(client)
    resp = await client.get("/api/v1/omnichannel/sweep-status", headers=auth_headers(token))
    assert resp.status_code == 403, resp.text
