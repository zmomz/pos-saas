"""Phase D — agent default language propagation (L10N-05)."""
from conftest import (
    auth_headers,
    make_agent_account,
    make_client_under_agent,
    unique_email,
)


async def test_agent_sets_default_language_and_it_is_returned(client):
    _user, token, _agent_id = await make_agent_account(client)
    headers = auth_headers(token)

    upd = await client.put(
        "/api/v1/branding/update", json={"default_language": "ar"}, headers=headers
    )
    assert upd.status_code == 200, upd.text
    assert upd.json()["default_language"] == "ar"

    branding = await client.get("/api/v1/tenant/agent/branding", headers=headers)
    assert branding.status_code == 200
    assert branding.json()["default_language"] == "ar"


async def test_new_client_inherits_agent_default_language(client):
    _user, token, _agent_id = await make_agent_account(client)
    headers = auth_headers(token)
    await client.put(
        "/api/v1/branding/update", json={"default_language": "ar"}, headers=headers
    )

    # No language_preference supplied → inherits the agent default ("ar").
    inherited = await client.post(
        "/api/v1/tenant/agent/clients",
        json={"business_name": "Shop A", "email": unique_email()},
        headers=headers,
    )
    assert inherited.status_code == 200, inherited.text
    assert inherited.json()["language_preference"] == "ar"

    # Explicit preference overrides the agent default.
    override = await client.post(
        "/api/v1/tenant/agent/clients",
        json={
            "business_name": "Shop B",
            "email": unique_email(),
            "language_preference": "en",
        },
        headers=headers,
    )
    assert override.status_code == 200, override.text
    assert override.json()["language_preference"] == "en"


async def test_client_branding_exposes_agent_default_language(client):
    _user, token, agent_id = await make_agent_account(client)
    await client.put(
        "/api/v1/branding/update",
        json={"default_language": "ur"},
        headers=auth_headers(token),
    )

    _cuser, ctoken, _cid = await make_client_under_agent(client, agent_id)
    branding = await client.get(
        "/api/v1/tenant/client/branding", headers=auth_headers(ctoken)
    )
    assert branding.status_code == 200, branding.text
    assert branding.json()["default_language"] == "ur"
