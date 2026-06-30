"""M5·CRM (#221) — customer groups & membership tiers (tracer bullet).

Acceptance: "Customers can belong to groups/tiers." A merchant defines named
customer groups (each carrying a tier label, e.g. wholesale/vip, and an optional
default discount), then assigns a customer to a group so the customer record
surfaces the membership. The server is authoritative and owner-scoped (SEC-02): a
tenant can neither see, assign to, nor through another tenant's group/customer.
"""
from conftest import auth_headers, make_client_account

GROUPS_URL = "/api/v1/entities/customers/groups"


async def _make_customer(client, token, name="Group Cust"):
    resp = await client.post(
        "/api/v1/entities/customers", json={"name": name}, headers=auth_headers(token)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _make_group(client, token, name="Wholesale", tier="gold", discount_percent=10):
    resp = await client.post(
        GROUPS_URL,
        json={"name": name, "tier": tier, "discount_percent": discount_percent},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_and_list_customer_groups(client):
    _, token, _ = await make_client_account(client)

    # No groups yet.
    r0 = await client.get(GROUPS_URL, headers=auth_headers(token))
    assert r0.status_code == 200, r0.text
    assert r0.json()["items"] == []

    group = await _make_group(client, token, name="Wholesale", tier="gold", discount_percent=10)
    assert group["name"] == "Wholesale"
    assert group["tier"] == "gold"
    assert group["discount_percent"] == 10.0

    r1 = await client.get(GROUPS_URL, headers=auth_headers(token))
    assert r1.status_code == 200, r1.text
    names = {g["name"]: g for g in r1.json()["items"]}
    assert "Wholesale" in names
    assert names["Wholesale"]["tier"] == "gold"


async def test_assign_customer_to_group_and_unassign(client):
    _, token, _ = await make_client_account(client)
    cust_id = await _make_customer(client, token)
    group = await _make_group(client, token)

    # Fresh customer belongs to no group.
    before = await client.get(
        f"/api/v1/entities/customers/{cust_id}", headers=auth_headers(token)
    )
    assert before.json()["group_id"] is None

    # Assign the customer to the group.
    assigned = await client.post(
        f"/api/v1/entities/customers/{cust_id}/group",
        json={"group_id": group["id"]},
        headers=auth_headers(token),
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["group_id"] == group["id"]

    # The membership persists on the customer record.
    after = await client.get(
        f"/api/v1/entities/customers/{cust_id}", headers=auth_headers(token)
    )
    assert after.json()["group_id"] == group["id"]

    # Unassign clears the membership.
    cleared = await client.delete(
        f"/api/v1/entities/customers/{cust_id}/group", headers=auth_headers(token)
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["group_id"] is None


async def test_customer_groups_are_owner_scoped(client):
    _, token_a, _ = await make_client_account(client)
    _, token_b, _ = await make_client_account(client)
    group_a = await _make_group(client, token_a, name="A-only")
    cust_a = await _make_customer(client, token_a)
    cust_b = await _make_customer(client, token_b)

    # Tenant B cannot see tenant A's groups.
    listing = await client.get(GROUPS_URL, headers=auth_headers(token_b))
    assert listing.status_code == 200, listing.text
    assert all(g["name"] != "A-only" for g in listing.json()["items"])

    # Tenant B cannot assign their own customer into tenant A's group (foreign group → 404).
    cross_group = await client.post(
        f"/api/v1/entities/customers/{cust_b}/group",
        json={"group_id": group_a["id"]},
        headers=auth_headers(token_b),
    )
    assert cross_group.status_code == 404, cross_group.text

    # Tenant B cannot assign tenant A's customer at all (foreign customer → 404).
    group_b = await _make_group(client, token_b, name="B-grp")
    cross_cust = await client.post(
        f"/api/v1/entities/customers/{cust_a}/group",
        json={"group_id": group_b["id"]},
        headers=auth_headers(token_b),
    )
    assert cross_cust.status_code == 404, cross_cust.text

    # Tenant A's customer is untouched by B's attempts.
    a_view = await client.get(
        f"/api/v1/entities/customers/{cust_a}", headers=auth_headers(token_a)
    )
    assert a_view.json()["group_id"] is None
