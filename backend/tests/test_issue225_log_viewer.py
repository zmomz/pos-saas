"""ISSUE-225 (M10 Admin) — error/API log viewer (admin-console slice).

The fourth end-to-end slice of the operator admin console (after maintenance
mode, the feature-flag console, and the job/queue monitor): a platform master
can read a **read-only viewer** of the per-request API log (``api_usage``) from
an admin endpoint, and the rows are real, never fabricated:

- the master reads the request log **platform-wide** — every tenant's requests,
  not just their own — newest-first and paginated;
- an ``errors_only`` filter narrows the viewer to failing requests
  (``status_code >= 400``), which is the "error log" view operators reach for;
- a non-master tenant cannot read the platform log viewer (403).
"""
import uuid

import pytest

from core.database import db_manager
from models.api_usage import Api_usage

from conftest import auth_headers, make_client_account, make_master_account


async def _seed_api_usage(rows):
    """Insert raw ``api_usage`` rows (as the request middleware would) for the test."""
    async with db_manager.async_session_maker() as db:
        for r in rows:
            db.add(Api_usage(**r))
        await db.commit()


async def _read_logs(client, headers, **params):
    return await client.get("/api/v1/admin/logs/api", headers=headers, params=params)


@pytest.mark.asyncio
async def test_master_reads_api_log_platform_wide(client):
    """The master reads the request log across ALL tenants, newest-first, paginated."""
    _user, token = await make_master_account(client)
    headers = auth_headers(token)

    owner_a, owner_b = str(uuid.uuid4()), str(uuid.uuid4())
    await _seed_api_usage(
        [
            {"user_id": owner_a, "owner_user_id": owner_a, "endpoint": "/api/v1/products", "method": "GET", "status_code": 200},
            {"user_id": owner_b, "owner_user_id": owner_b, "endpoint": "/api/v1/pos/transaction", "method": "POST", "status_code": 201},
        ]
    )

    resp = await _read_logs(client, headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total"] == 2
    owners = {row["owner_user_id"] for row in body["items"]}
    assert owners == {owner_a, owner_b}  # platform-wide, both tenants surfaced

    # Newest-first (highest id first), never fabricated — real endpoints/methods.
    ids = [row["id"] for row in body["items"]]
    assert ids == sorted(ids, reverse=True)
    first = body["items"][0]
    assert {"endpoint", "method", "status_code"}.issubset(first.keys())


@pytest.mark.asyncio
async def test_errors_only_narrows_to_failing_requests(client):
    """``errors_only`` returns only rows with status_code >= 400 — the error-log view."""
    _user, token = await make_master_account(client)
    headers = auth_headers(token)

    owner = str(uuid.uuid4())
    await _seed_api_usage(
        [
            {"user_id": owner, "owner_user_id": owner, "endpoint": "/api/v1/products", "method": "GET", "status_code": 200},
            {"user_id": owner, "owner_user_id": owner, "endpoint": "/api/v1/orders", "method": "POST", "status_code": 500},
            {"user_id": owner, "owner_user_id": owner, "endpoint": "/api/v1/login", "method": "POST", "status_code": 401},
        ]
    )

    resp = await _read_logs(client, headers, errors_only=True)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total"] == 2
    assert all(row["status_code"] >= 400 for row in body["items"])


@pytest.mark.asyncio
async def test_non_master_cannot_read_log_viewer(client):
    """A tenant operator has no business reading the platform log viewer (403)."""
    _user, token, _client_id = await make_client_account(client)
    headers = auth_headers(token)

    assert (await _read_logs(client, headers)).status_code == 403
