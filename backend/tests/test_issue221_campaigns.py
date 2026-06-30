"""M5·CRM (#221) — marketing campaigns (tracer bullet).

Acceptance: "Campaigns ... function." A merchant defines a named campaign on a
channel (sms/email) carrying a message, optionally targeting one customer group.
The campaign reports its **audience** — how many of the merchant's customers it
would reach (the targeted group, or every customer when untargeted) — so it is a
real, queryable artifact and not just a label. The server is authoritative and
owner-scoped (SEC-02): a tenant can neither see another tenant's campaigns nor
target another tenant's group.
"""
from conftest import auth_headers, make_client_account

CAMPAIGNS_URL = "/api/v1/entities/customers/campaigns"
GROUPS_URL = "/api/v1/entities/customers/groups"


async def _make_customer(client, token, name="Camp Cust", group_id=None):
    resp = await client.post(
        "/api/v1/entities/customers", json={"name": name}, headers=auth_headers(token)
    )
    assert resp.status_code == 201, resp.text
    cust = resp.json()
    if group_id is not None:
        a = await client.post(
            f"/api/v1/entities/customers/{cust['id']}/group",
            json={"group_id": group_id},
            headers=auth_headers(token),
        )
        assert a.status_code == 200, a.text
    return cust["id"]


async def _make_group(client, token, name="VIP"):
    resp = await client.post(
        GROUPS_URL,
        json={"name": name, "tier": "gold"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_and_list_campaigns(client):
    _, token, _ = await make_client_account(client)

    # No campaigns yet.
    r0 = await client.get(CAMPAIGNS_URL, headers=auth_headers(token))
    assert r0.status_code == 200, r0.text
    assert r0.json()["items"] == []

    created = await client.post(
        CAMPAIGNS_URL,
        json={"name": "Eid Sale", "channel": "sms", "message": "20% off!"},
        headers=auth_headers(token),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "Eid Sale"
    assert body["channel"] == "sms"
    assert body["message"] == "20% off!"
    assert body["status"] == "draft"
    assert body["target_group_id"] is None

    r1 = await client.get(CAMPAIGNS_URL, headers=auth_headers(token))
    assert r1.status_code == 200, r1.text
    names = {c["name"] for c in r1.json()["items"]}
    assert "Eid Sale" in names


async def test_campaign_reports_audience_count(client):
    _, token, _ = await make_client_account(client)
    group = await _make_group(client, token, name="VIP")

    # Two customers in the group, one outside it.
    await _make_customer(client, token, name="In-1", group_id=group["id"])
    await _make_customer(client, token, name="In-2", group_id=group["id"])
    await _make_customer(client, token, name="Out", group_id=None)

    # A campaign targeting the group reaches only its members.
    targeted = await client.post(
        CAMPAIGNS_URL,
        json={"name": "VIP Push", "channel": "email", "message": "hi",
              "target_group_id": group["id"]},
        headers=auth_headers(token),
    )
    assert targeted.status_code == 201, targeted.text
    assert targeted.json()["target_group_id"] == group["id"]
    assert targeted.json()["audience_count"] == 2

    # An untargeted campaign reaches every customer.
    broad = await client.post(
        CAMPAIGNS_URL,
        json={"name": "Everyone", "channel": "sms", "message": "hi"},
        headers=auth_headers(token),
    )
    assert broad.status_code == 201, broad.text
    assert broad.json()["audience_count"] == 3


async def test_campaigns_are_owner_scoped(client):
    _, token_a, _ = await make_client_account(client)
    _, token_b, _ = await make_client_account(client)
    group_a = await _make_group(client, token_a, name="A-grp")

    await client.post(
        CAMPAIGNS_URL,
        json={"name": "A-only", "channel": "sms", "message": "x"},
        headers=auth_headers(token_a),
    )

    # Tenant B cannot see tenant A's campaigns.
    listing = await client.get(CAMPAIGNS_URL, headers=auth_headers(token_b))
    assert listing.status_code == 200, listing.text
    assert all(c["name"] != "A-only" for c in listing.json()["items"])

    # Tenant B cannot target tenant A's group (foreign group → 404).
    cross = await client.post(
        CAMPAIGNS_URL,
        json={"name": "steal", "channel": "sms", "message": "x",
              "target_group_id": group_a["id"]},
        headers=auth_headers(token_b),
    )
    assert cross.status_code == 404, cross.text
