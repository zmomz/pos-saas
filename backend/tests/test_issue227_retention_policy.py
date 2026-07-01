"""M7·Compliance (#227) — data-retention policy for inactive customer PII.

Scope item: "Data-retention policy". PDPL (SEC-05) data-minimization obliges the
merchant (the data controller) not to keep personal data longer than necessary.
This pins a tenant-configurable retention window for *dormant* customer PII: the
merchant sets how many days a customer may sit untouched before their personal
data is minimized, and enforcement applies the existing PDPL erasure (tombstone
the name, null phone/email/VAT/notes, withdraw consent, stamp ``pii_erased_at``)
to everyone past the window.

Erasure — not deletion — is deliberate: the fiscal row is retained so ZATCA's
6-year invoice-retention obligation (which overrides erasure for fiscal records)
still holds; only the personal data is minimized.

The server is authoritative and owner-scoped (SEC-02): one tenant can neither
read nor mutate another tenant's policy, and enforcement never reaches across
tenants.
"""
from datetime import datetime, timedelta

from sqlalchemy import update

from conftest import auth_headers, make_client_account, db_manager
from models.customers import Customers

CUSTOMERS = "/api/v1/entities/customers"
POLICY = f"{CUSTOMERS}/retention-policy"
ENFORCE = f"{POLICY}/enforce"


async def _make_customer(client, token, **fields):
    body = {"name": "Retention Cust"}
    body.update(fields)
    resp = await client.post(CUSTOMERS, json=body, headers=auth_headers(token))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _backdate(customer_id, days):
    """Age a customer's ``updated_at`` so it reads as dormant for ``days`` days."""
    old = datetime.now() - timedelta(days=days)
    async with db_manager.async_session_maker() as db:
        await db.execute(
            update(Customers).where(Customers.id == customer_id).values(updated_at=old)
        )
        await db.commit()


async def test_policy_defaults_to_unset(client):
    _, token, _ = await make_client_account(client)
    r = await client.get(POLICY, headers=auth_headers(token))
    assert r.status_code == 200, r.text
    assert r.json()["customer_pii_retention_days"] is None


async def test_policy_is_settable_and_readable(client):
    _, token, _ = await make_client_account(client)
    u = await client.put(
        POLICY, json={"customer_pii_retention_days": 365}, headers=auth_headers(token)
    )
    assert u.status_code == 200, u.text
    assert u.json()["customer_pii_retention_days"] == 365

    r = await client.get(POLICY, headers=auth_headers(token))
    assert r.json()["customer_pii_retention_days"] == 365


async def test_policy_rejects_non_positive_window(client):
    _, token, _ = await make_client_account(client)
    for bad in (0, -5):
        u = await client.put(
            POLICY,
            json={"customer_pii_retention_days": bad},
            headers=auth_headers(token),
        )
        assert u.status_code == 422 or u.status_code == 400, (bad, u.text)


async def test_policy_null_disables_retention(client):
    _, token, _ = await make_client_account(client)
    await client.put(
        POLICY, json={"customer_pii_retention_days": 30}, headers=auth_headers(token)
    )
    u = await client.put(
        POLICY, json={"customer_pii_retention_days": None}, headers=auth_headers(token)
    )
    assert u.status_code == 200, u.text
    assert u.json()["customer_pii_retention_days"] is None


async def test_policy_is_owner_scoped(client):
    _, token_a, _ = await make_client_account(client)
    _, token_b, _ = await make_client_account(client)
    await client.put(
        POLICY, json={"customer_pii_retention_days": 90}, headers=auth_headers(token_a)
    )
    rb = await client.get(POLICY, headers=auth_headers(token_b))
    # B has its own (unset) policy — it never sees A's window.
    assert rb.json()["customer_pii_retention_days"] is None


async def test_enforce_without_policy_erases_nothing(client):
    _, token, _ = await make_client_account(client)
    cid = await _make_customer(client, token, phone="0500000000")
    await _backdate(cid, days=9999)

    e = await client.post(ENFORCE, headers=auth_headers(token))
    assert e.status_code == 200, e.text
    assert e.json()["erased_count"] == 0

    r = await client.get(f"{CUSTOMERS}/{cid}", headers=auth_headers(token))
    assert r.json()["phone"] == "0500000000"
    assert r.json()["pii_erased_at"] is None


async def test_enforce_erases_dormant_customer_pii(client):
    _, token, _ = await make_client_account(client)
    cid = await _make_customer(
        client, token, phone="0500000000", email="x@y.z", marketing_consent=True
    )
    await client.put(
        POLICY, json={"customer_pii_retention_days": 365}, headers=auth_headers(token)
    )
    await _backdate(cid, days=400)

    e = await client.post(ENFORCE, headers=auth_headers(token))
    assert e.status_code == 200, e.text
    assert e.json()["erased_count"] == 1
    assert cid in e.json()["erased"]

    r = await client.get(f"{CUSTOMERS}/{cid}", headers=auth_headers(token))
    body = r.json()
    assert body["name"] == "[erased]"
    assert body["phone"] is None
    assert body["email"] is None
    assert body["marketing_consent"] is False
    assert body["pii_erased_at"] is not None

    # Erasure withdrew consent — the trail evidences it (#227 consent history).
    h = await client.get(
        f"{CUSTOMERS}/{cid}/consent-history", headers=auth_headers(token)
    )
    items = h.json()["items"]
    assert items[0]["granted"] is False
    assert items[0]["source"] == "erase"


async def test_enforce_spares_recently_active_customer(client):
    _, token, _ = await make_client_account(client)
    cid = await _make_customer(client, token, phone="0500000000")
    await client.put(
        POLICY, json={"customer_pii_retention_days": 365}, headers=auth_headers(token)
    )
    await _backdate(cid, days=100)  # inside the window

    e = await client.post(ENFORCE, headers=auth_headers(token))
    assert e.json()["erased_count"] == 0

    r = await client.get(f"{CUSTOMERS}/{cid}", headers=auth_headers(token))
    assert r.json()["phone"] == "0500000000"


async def test_enforce_skips_already_erased(client):
    _, token, _ = await make_client_account(client)
    cid = await _make_customer(
        client, token, phone="0500000000", marketing_consent=True
    )
    await client.put(
        POLICY, json={"customer_pii_retention_days": 30}, headers=auth_headers(token)
    )
    await _backdate(cid, days=100)

    first = await client.post(ENFORCE, headers=auth_headers(token))
    assert first.json()["erased_count"] == 1
    # Re-running is idempotent — the already-tombstoned row is not re-erased and
    # no spurious consent-withdrawal event is appended.
    await _backdate(cid, days=100)
    second = await client.post(ENFORCE, headers=auth_headers(token))
    assert second.json()["erased_count"] == 0

    h = await client.get(
        f"{CUSTOMERS}/{cid}/consent-history", headers=auth_headers(token)
    )
    erase_events = [e for e in h.json()["items"] if e["source"] == "erase"]
    assert len(erase_events) == 1


async def test_enforce_is_owner_scoped(client):
    _, token_a, _ = await make_client_account(client)
    _, token_b, _ = await make_client_account(client)
    cid_a = await _make_customer(client, token_a, phone="0500000000")
    await _backdate(cid_a, days=999)

    # B sets an aggressive policy and enforces — A's customer must be untouched.
    await client.put(
        POLICY, json={"customer_pii_retention_days": 1}, headers=auth_headers(token_b)
    )
    e = await client.post(ENFORCE, headers=auth_headers(token_b))
    assert e.json()["erased_count"] == 0

    r = await client.get(f"{CUSTOMERS}/{cid_a}", headers=auth_headers(token_a))
    assert r.json()["phone"] == "0500000000"
