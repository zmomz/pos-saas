"""F-014 (POS-12, P0 [market]): the offline sync endpoint bounds a single
request. The frontend flushes the IndexedDB backlog in bounded chunks; the
backend refuses one giant payload as defence-in-depth.

Before the fix the endpoint iterated whatever was posted, so an oversized
backlog was accepted (200) and processed in one request.
"""
import pytest

from conftest import auth_headers, make_client_account
from routers.production import MAX_OFFLINE_SYNC_BATCH


@pytest.mark.asyncio
async def test_offline_sync_rejects_oversized_batch(client):
    _, token, client_id = await make_client_account(client)

    oversized = {
        "transactions": [
            {
                "offline_id": f"OFFLINE-CAP-{i}",
                "client_id": client_id,
                "total_amount": 1.0,
                "payment_method": "cash",
                "items": [],
            }
            for i in range(MAX_OFFLINE_SYNC_BATCH + 1)
        ]
    }

    resp = await client.post(
        "/api/v1/production/offline/sync",
        headers=auth_headers(token),
        json=oversized,
    )
    assert resp.status_code == 413, resp.text
    assert str(MAX_OFFLINE_SYNC_BATCH) in resp.json()["detail"]


@pytest.mark.asyncio
async def test_offline_sync_accepts_a_batch_at_the_cap_boundary(client):
    """A request of exactly MAX_OFFLINE_SYNC_BATCH items is not rejected by the
    guard (it is processed normally — here a single real sale proves the
    boundary check uses ``>`` not ``>=``)."""
    _, token, client_id = await make_client_account(client)

    assert MAX_OFFLINE_SYNC_BATCH >= 500  # POS-12 floor

    resp = await client.post(
        "/api/v1/production/offline/sync",
        headers=auth_headers(token),
        json={
            "transactions": [
                {
                    "offline_id": "OFFLINE-BOUNDARY-1",
                    "client_id": client_id,
                    "total_amount": 10.0,
                    "payment_method": "cash",
                    "items": [],
                }
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["processed"] == 1
