"""ISSUE-225 (M10 Admin) — feature-flag console (admin-console slice).

The second end-to-end slice of the operator admin console (after maintenance
mode): a platform master can read and edit **platform-global feature flags** from
an admin endpoint, and the server is authoritative:

- the master reads the declared flag registry with each flag's real persisted
  value (defaults applied — nothing fabricated);
- the master toggles a flag and it persists across reads;
- toggling a flag the platform does not declare is refused (no cosmetic switches);
- a non-master tenant can neither read nor edit platform flags (403);
- at least one flag drives real behaviour end-to-end: turning ``self_registration``
  off refuses self-serve registration even while the static config allows it.
"""
import pytest

from conftest import auth_headers, make_client_account, make_master_account, unique_email


async def _list_flags(client, headers):
    return await client.get("/api/v1/admin/feature-flags", headers=headers)


async def _set_flag(client, headers, key, enabled):
    return await client.put(
        f"/api/v1/admin/feature-flags/{key}",
        json={"enabled": enabled},
        headers=headers,
    )


@pytest.mark.asyncio
async def test_master_reads_declared_flag_registry_with_defaults(client):
    """The master reads the declared flags, each with its default (persisted) value."""
    _user, token = await make_master_account(client)
    headers = auth_headers(token)

    resp = await _list_flags(client, headers)
    assert resp.status_code == 200, resp.text
    flags = {f["key"]: f for f in resp.json()}

    # The registry is real and declared, not fabricated: self_registration ships on.
    assert "self_registration" in flags
    assert flags["self_registration"]["enabled"] is True
    assert flags["self_registration"]["description"]


@pytest.mark.asyncio
async def test_master_toggles_flag_and_it_persists(client):
    """The master flips a declared flag off and back on; each change survives a re-read."""
    _user, token = await make_master_account(client)
    headers = auth_headers(token)

    off = await _set_flag(client, headers, "self_registration", False)
    assert off.status_code == 200, off.text
    assert off.json() == {
        "key": "self_registration",
        "enabled": False,
        "description": off.json()["description"],
    }

    got = {f["key"]: f for f in (await _list_flags(client, headers)).json()}
    assert got["self_registration"]["enabled"] is False

    on = await _set_flag(client, headers, "self_registration", True)
    assert on.status_code == 200, on.text
    got = {f["key"]: f for f in (await _list_flags(client, headers)).json()}
    assert got["self_registration"]["enabled"] is True


@pytest.mark.asyncio
async def test_toggling_an_undeclared_flag_is_refused(client):
    """The console only stores real declared flags — an unknown name is rejected (400)."""
    _user, token = await make_master_account(client)
    headers = auth_headers(token)

    resp = await _set_flag(client, headers, "totally_made_up_flag", True)
    assert resp.status_code == 400, resp.text
    # And nothing was persisted for it.
    keys = {f["key"] for f in (await _list_flags(client, headers)).json()}
    assert "totally_made_up_flag" not in keys


@pytest.mark.asyncio
async def test_non_master_cannot_read_or_edit_flags(client):
    """A tenant operator can neither read nor edit platform feature flags (403)."""
    _user, token, _client_id = await make_client_account(client)
    headers = auth_headers(token)

    assert (await _list_flags(client, headers)).status_code == 403
    assert (await _set_flag(client, headers, "self_registration", False)).status_code == 403


@pytest.mark.asyncio
async def test_self_registration_flag_gates_registration(client):
    """Turning the ``self_registration`` flag off refuses self-serve registration (403).

    The static config still allows registration (conftest sets ALLOW_REGISTRATION),
    so this proves the runtime flag is authoritative and drives real behaviour.
    """
    # Create the master FIRST (while registration is still on) so they can toggle.
    _user, token = await make_master_account(client)
    headers = auth_headers(token)

    # Baseline: a fresh self-registration succeeds.
    ok = await client.post(
        "/api/v1/auth/register",
        json={"email": unique_email(), "password": "Password123", "name": "Before"},
    )
    assert ok.status_code == 201, ok.text

    # Master flips the flag off.
    assert (await _set_flag(client, headers, "self_registration", False)).status_code == 200

    # Now the same self-registration call is refused, despite the static allow.
    blocked = await client.post(
        "/api/v1/auth/register",
        json={"email": unique_email(), "password": "Password123", "name": "After"},
    )
    assert blocked.status_code == 403, blocked.text

    # Turning it back on restores registration.
    assert (await _set_flag(client, headers, "self_registration", True)).status_code == 200
    restored = await client.post(
        "/api/v1/auth/register",
        json={"email": unique_email(), "password": "Password123", "name": "Restored"},
    )
    assert restored.status_code == 201, restored.text
