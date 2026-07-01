"""ISSUE-225 (M10 Admin) — maintenance mode (admin-console tracer bullet).

The first end-to-end slice of the operator admin console: a platform master can
toggle a global **maintenance mode**, and the server is authoritative about what
that means:

- the master reads/writes the maintenance flag from an admin endpoint (default off);
- a non-master tenant cannot see or change it (403);
- while maintenance is ON, ordinary tenant API traffic is refused with 503;
- the master is never locked out — they can still reach the API (and the toggle)
  to turn maintenance back off.
"""
import pytest

from conftest import auth_headers, make_client_account, make_master_account


async def _get_maintenance(client, headers):
    return await client.get("/api/v1/admin/maintenance", headers=headers)


async def _set_maintenance(client, headers, enabled, message=None):
    return await client.put(
        "/api/v1/admin/maintenance",
        json={"enabled": enabled, "message": message},
        headers=headers,
    )


@pytest.mark.asyncio
async def test_master_reads_default_disabled_state(client):
    """Maintenance mode is off by default; the master can read that state."""
    _user, token = await make_master_account(client)
    headers = auth_headers(token)

    resp = await _get_maintenance(client, headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["enabled"] is False
    assert body.get("message") is None


@pytest.mark.asyncio
async def test_master_toggles_maintenance_on_and_off(client):
    """The master turns maintenance on (with a message) and back off; it persists."""
    _user, token = await make_master_account(client)
    headers = auth_headers(token)

    on = await _set_maintenance(client, headers, True, message="Upgrading — back at 5pm")
    assert on.status_code == 200, on.text
    assert on.json() == {"enabled": True, "message": "Upgrading — back at 5pm"}

    # The written state survives a fresh read.
    got = await _get_maintenance(client, headers)
    assert got.json() == {"enabled": True, "message": "Upgrading — back at 5pm"}

    off = await _set_maintenance(client, headers, False)
    assert off.status_code == 200, off.text
    assert off.json()["enabled"] is False
    assert (await _get_maintenance(client, headers)).json()["enabled"] is False


@pytest.mark.asyncio
async def test_non_master_cannot_read_or_toggle(client):
    """A tenant operator can neither read nor change platform maintenance mode (403)."""
    _user, token, _client_id = await make_client_account(client)
    headers = auth_headers(token)

    assert (await _get_maintenance(client, headers)).status_code == 403
    assert (await _set_maintenance(client, headers, True)).status_code == 403


@pytest.mark.asyncio
async def test_maintenance_refuses_tenant_traffic_with_503(client):
    """While maintenance is ON, an ordinary tenant API call is refused with 503."""
    _muser, mtoken = await make_master_account(client)
    _user, token, _client_id = await make_client_account(client)
    client_headers = auth_headers(token)

    # Baseline: the tenant can list products before maintenance.
    ok = await client.get("/api/v1/entities/products", headers=client_headers)
    assert ok.status_code == 200, ok.text

    # Master flips maintenance on.
    await _set_maintenance(client, auth_headers(mtoken), True, message="Down for maintenance")

    # Now the same tenant call is refused.
    blocked = await client.get("/api/v1/entities/products", headers=client_headers)
    assert blocked.status_code == 503, blocked.text
    assert "maintenance" in blocked.json()["detail"].lower()


@pytest.mark.asyncio
async def test_master_is_never_locked_out_during_maintenance(client):
    """While maintenance is ON, the master still reaches the API and can toggle it off."""
    _muser, mtoken = await make_master_account(client)
    mheaders = auth_headers(mtoken)

    await _set_maintenance(client, mheaders, True)

    # A general tenant endpoint is still reachable for the master (not 503).
    passthru = await client.get("/api/v1/entities/products", headers=mheaders)
    assert passthru.status_code != 503, passthru.text

    # The admin console stays reachable so the master can turn maintenance back off.
    off = await _set_maintenance(client, mheaders, False)
    assert off.status_code == 200, off.text
    assert off.json()["enabled"] is False
