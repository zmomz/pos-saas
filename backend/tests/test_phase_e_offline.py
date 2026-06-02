"""Phase E — offline transaction sync idempotency."""
import pytest

from conftest import auth_headers, make_client_account


@pytest.mark.asyncio
async def test_offline_sync_is_idempotent(client):
    user, token, client_id = await make_client_account(client)

    queued = {
        "transactions": [
            {
                "offline_id": "OFFLINE-ABC123",
                "client_id": client_id,
                "subtotal": 50.0,
                "vat_amount": 7.5,
                "total_amount": 57.5,
                "payment_method": "cash",
                "items": [{"product_id": 1, "name": "W", "price": 50, "quantity": 1}],
            }
        ]
    }

    first = await client.post(
        "/api/v1/production/offline/sync", headers=auth_headers(token), json=queued
    )
    assert first.status_code == 200, first.text
    assert first.json()["processed"] == 1
    assert first.json()["skipped_duplicates"] == 0

    # Replaying the same queue (e.g. a flaky reconnect) must not double-insert.
    second = await client.post(
        "/api/v1/production/offline/sync", headers=auth_headers(token), json=queued
    )
    assert second.status_code == 200, second.text
    assert second.json()["processed"] == 0
    assert second.json()["skipped_duplicates"] == 1


@pytest.mark.asyncio
async def test_offline_sync_empty_rejected(client):
    _, token, _ = await make_client_account(client)
    resp = await client.post(
        "/api/v1/production/offline/sync",
        headers=auth_headers(token),
        json={"transactions": []},
    )
    assert resp.status_code == 400
