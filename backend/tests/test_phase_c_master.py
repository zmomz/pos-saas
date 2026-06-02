"""Phase C — master agent provisioning, slot refill, and global tax rate."""
from conftest import (
    auth_headers,
    make_client_account,
    make_master_account,
    unique_email,
)


async def test_master_creates_agent_with_login(client):
    _, master_token = await make_master_account(client)
    agent_email = unique_email()

    resp = await client.post(
        "/api/v1/tenant/master/agents",
        json={"company_name": "Acme Resell", "email": agent_email, "slots": 3},
        headers=auth_headers(master_token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["package_type"] == 3
    assert body["used_slots"] == 0
    temp_password = body["temp_password"]
    assert temp_password

    # The provisioned agent can actually log in...
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": agent_email, "password": temp_password},
    )
    assert login.status_code == 200, login.text
    agent_token = login.json()["token"]

    # ...and resolves as an agent.
    role = await client.get("/api/v1/tenant/role", headers=auth_headers(agent_token))
    assert role.status_code == 200
    assert role.json()["role"] == "agent"


async def test_create_agent_requires_master(client):
    # A tenancy client must not be able to create agents.
    _, token, _ = await make_client_account(client)
    resp = await client.post(
        "/api/v1/tenant/master/agents",
        json={"company_name": "X", "email": unique_email(), "slots": 1},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


async def test_create_agent_rejects_duplicate_email(client):
    _, master_token = await make_master_account(client)
    email = unique_email()
    payload = {"company_name": "Dup", "email": email, "slots": 1}
    first = await client.post(
        "/api/v1/tenant/master/agents", json=payload, headers=auth_headers(master_token)
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/tenant/master/agents", json=payload, headers=auth_headers(master_token)
    )
    assert second.status_code == 409


async def test_master_adds_agent_slots(client):
    _, master_token = await make_master_account(client)
    created = await client.post(
        "/api/v1/tenant/master/agents",
        json={"company_name": "Grow", "email": unique_email(), "slots": 2},
        headers=auth_headers(master_token),
    )
    agent_id = created.json()["id"]

    resp = await client.post(
        f"/api/v1/tenant/master/agents/{agent_id}/slots",
        json={"slots": 5},
        headers=auth_headers(master_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["package_type"] == 7
    assert body["remaining_slots"] == 7


async def test_global_tax_rate_set_get_and_enforcement(client):
    _, master_token = await make_master_account(client)

    # Default (no global rate) reports the statutory fallback, not global.
    default = await client.get("/api/v1/tenant/tax-rate", headers=auth_headers(master_token))
    assert default.status_code == 200
    assert default.json()["is_global"] is False

    # Master sets a global rate.
    set_resp = await client.put(
        "/api/v1/tenant/master/tax-rate",
        json={"tax_rate": 5.0},
        headers=auth_headers(master_token),
    )
    assert set_resp.status_code == 200, set_resp.text
    assert set_resp.json() == {"tax_rate": 5.0, "is_global": True}

    # A client inherits it and a POS sale uses it (overriding the request's 15).
    user, token, client_id = await make_client_account(client)
    from conftest import add_product

    pid = await add_product(client_id, user["id"], name="TaxItem", quantity=10, price=100.0)
    sale = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "TaxItem", "price": 100.0, "quantity": 1}],
            "payment_method": "cash",
            "vat_rate": 15.0,  # must be ignored in favour of the 5% global rate
        },
        headers=auth_headers(token),
    )
    assert sale.status_code == 200, sale.text
    assert sale.json()["vat_amount"] == 5.0  # 5% of 100, not 15

    # Non-master cannot change the global rate.
    forbidden = await client.put(
        "/api/v1/tenant/master/tax-rate",
        json={"tax_rate": 20.0},
        headers=auth_headers(token),
    )
    assert forbidden.status_code == 403

    # Reset so the global rate does not leak into other tests.
    from core.database import db_manager
    from services.system_settings import GLOBAL_TAX_RATE_KEY, set_setting

    async with db_manager.async_session_maker() as db:
        await set_setting(db, GLOBAL_TAX_RATE_KEY, "")
        await db.commit()
