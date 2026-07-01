"""M7·Compliance (#227) — queryable consent history (tracer bullet).

Scope item: "Consent history". PDPL (SEC-05) obliges the merchant (the data
controller) to be able to *evidence* when marketing consent was given or withdrawn.
The customer row only carries the LATEST state (``marketing_consent`` +
``consent_updated_at``); ``consent_updated_at`` is overwritten on every change, so
the audit trail of "given on X, withdrawn on Y, re-given on Z" is lost.

This pins the append-only consent-event log behind that snapshot: each consent
change (at create, on update, and on PDPL erasure) writes its own immutable,
timestamped row, and the history endpoint reads them back newest-first.

The server is authoritative and owner-scoped (SEC-02): a tenant can neither read
another tenant's consent history — a foreign/unknown customer 404s.
"""
from conftest import auth_headers, make_client_account

CUSTOMERS = "/api/v1/entities/customers"


async def _make_customer(client, token, **fields):
    body = {"name": "Consent Cust"}
    body.update(fields)
    resp = await client.post(CUSTOMERS, json=body, headers=auth_headers(token))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _history_url(cid):
    return f"{CUSTOMERS}/{cid}/consent-history"


async def test_consent_given_at_create_is_recorded(client):
    _, token, _ = await make_client_account(client)
    cid = await _make_customer(client, token, marketing_consent=True)

    r = await client.get(_history_url(cid), headers=auth_headers(token))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    ev = items[0]
    assert ev["granted"] is True
    assert ev["source"] == "create"
    assert ev["created_at"] is not None


async def test_no_event_when_consent_not_supplied(client):
    # Default-off (silence is not consent) is not an explicit opt-in decision, so
    # creating a customer without a consent flag records nothing.
    _, token, _ = await make_client_account(client)
    cid = await _make_customer(client, token)

    r = await client.get(_history_url(cid), headers=auth_headers(token))
    assert r.status_code == 200, r.text
    assert r.json()["items"] == []


async def test_consent_changes_append_newest_first(client):
    _, token, _ = await make_client_account(client)
    cid = await _make_customer(client, token, marketing_consent=True)

    # Withdraw, then re-grant — each change appends its own row.
    for granted in (False, True):
        u = await client.put(
            f"{CUSTOMERS}/{cid}",
            json={"marketing_consent": granted},
            headers=auth_headers(token),
        )
        assert u.status_code == 200, u.text

    r = await client.get(_history_url(cid), headers=auth_headers(token))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    # Append-only, newest-first: re-grant (True), withdrawal (False), create (True).
    assert [e["granted"] for e in items] == [True, False, True]
    assert [e["source"] for e in items] == ["update", "update", "create"]


async def test_no_event_when_update_leaves_consent_unchanged(client):
    # Re-sending the same consent value is a no-op — no spurious history row.
    _, token, _ = await make_client_account(client)
    cid = await _make_customer(client, token, marketing_consent=True)

    u = await client.put(
        f"{CUSTOMERS}/{cid}",
        json={"marketing_consent": True, "name": "Renamed"},
        headers=auth_headers(token),
    )
    assert u.status_code == 200, u.text

    r = await client.get(_history_url(cid), headers=auth_headers(token))
    items = r.json()["items"]
    assert [e["source"] for e in items] == ["create"]


async def test_erasure_records_consent_withdrawal(client):
    _, token, _ = await make_client_account(client)
    cid = await _make_customer(client, token, marketing_consent=True)

    e = await client.post(f"{CUSTOMERS}/{cid}/erase", headers=auth_headers(token))
    assert e.status_code == 200, e.text

    r = await client.get(_history_url(cid), headers=auth_headers(token))
    items = r.json()["items"]
    assert items[0]["granted"] is False
    assert items[0]["source"] == "erase"


async def test_consent_history_is_owner_scoped(client):
    _, token_a, _ = await make_client_account(client)
    _, token_b, _ = await make_client_account(client)
    cid_a = await _make_customer(client, token_a, marketing_consent=True)

    rb = await client.get(_history_url(cid_a), headers=auth_headers(token_b))
    assert rb.status_code == 404, rb.text
