"""Phase C — per-client feature enforcement and the agent runtime toggle (AG-03)."""
from conftest import (
    add_product,
    auth_headers,
    make_agent_account,
    make_client_under_agent,
)


async def _sale_txn_id(client, token, client_id, user_id):
    pid = await add_product(client_id, user_id, name="Item", quantity=10, price=100.0)
    sale = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Item", "price": 100.0, "quantity": 1}],
            "payment_method": "cash",
        },
        headers=auth_headers(token),
    )
    assert sale.status_code == 200, sale.text
    return sale.json()["id"]


async def test_agent_can_disable_client_feature(client):
    agent_user, agent_token, agent_id = await make_agent_account(client)
    client_user, client_token, client_id = await make_client_under_agent(client, agent_id)

    txn_id = await _sale_txn_id(client, client_token, client_id, client_user["id"])

    # Feature enabled by default → emailing works.
    ok = await client.post(
        f"/api/v1/pos/transactions/{txn_id}/email",
        json={"to_email": "x@example.com"},
        headers=auth_headers(client_token),
    )
    assert ok.status_code == 200, ok.text

    # Agent disables the feature for this client at runtime.
    toggle = await client.post(
        f"/api/v1/tenant/agent/clients/{client_id}/features",
        json={"feature_name": "email_receipts", "is_enabled": False},
        headers=auth_headers(agent_token),
    )
    assert toggle.status_code == 200, toggle.text

    # Now the gated endpoint is blocked for the client.
    blocked = await client.post(
        f"/api/v1/pos/transactions/{txn_id}/email",
        json={"to_email": "x@example.com"},
        headers=auth_headers(client_token),
    )
    assert blocked.status_code == 403


async def test_agent_cannot_toggle_other_agents_client(client):
    _, _, agent_a = await make_agent_account(client)
    _, other_token, _ = await make_agent_account(client)
    _, _, client_id = await make_client_under_agent(client, agent_a)

    resp = await client.post(
        f"/api/v1/tenant/agent/clients/{client_id}/features",
        json={"feature_name": "email_receipts", "is_enabled": False},
        headers=auth_headers(other_token),
    )
    assert resp.status_code == 404


async def test_agent_can_suspend_client(client):
    agent_user, agent_token, agent_id = await make_agent_account(client)
    client_user, client_token, client_id = await make_client_under_agent(client, agent_id)

    # Suspend.
    toggle = await client.post(
        f"/api/v1/tenant/agent/clients/{client_id}/toggle",
        headers=auth_headers(agent_token),
    )
    assert toggle.status_code == 200, toggle.text
    assert toggle.json()["is_active"] is False

    # The suspended client is now blocked at authentication (CL-05).
    me = await client.get("/api/v1/tenant/role", headers=auth_headers(client_token))
    assert me.status_code == 403
