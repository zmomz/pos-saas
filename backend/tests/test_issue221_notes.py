"""M5·CRM (#221) — per-customer notes thread (tracer bullet).

Scope item: "notes". The single free-form ``customers.notes`` field is a snapshot;
a thread is the merchant's running log — append a dated note (a call summary, a
complaint, a follow-up reminder), then read the whole conversation newest-first.
Unlike the snapshot field each note is its own immutable, timestamped row, so the
history is preserved rather than overwritten.

The server is authoritative and owner-scoped (SEC-02): a tenant can neither read
nor append to another tenant's customer notes — a foreign/unknown customer 404s.
"""
from conftest import auth_headers, make_client_account


async def _make_customer(client, token, name="Notes Cust"):
    resp = await client.post(
        "/api/v1/entities/customers", json={"name": name}, headers=auth_headers(token)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _notes_url(cid):
    return f"/api/v1/entities/customers/{cid}/notes"


async def test_notes_thread_empty_then_appended_newest_first(client):
    _, token, _ = await make_client_account(client)
    cid = await _make_customer(client, token)

    # A fresh customer has an empty thread.
    r0 = await client.get(_notes_url(cid), headers=auth_headers(token))
    assert r0.status_code == 200, r0.text
    assert r0.json()["items"] == []

    # Append a note — it comes back as its own timestamped row.
    a = await client.post(
        _notes_url(cid),
        json={"body": "Called about a refund", "author": "Sara"},
        headers=auth_headers(token),
    )
    assert a.status_code == 201, a.text
    note = a.json()
    assert note["body"] == "Called about a refund"
    assert note["author"] == "Sara"
    assert note["created_at"] is not None

    # Append a second note; the thread reads newest-first and is append-only
    # (both notes survive — the thread is not overwritten).
    b = await client.post(
        _notes_url(cid),
        json={"body": "Refund issued"},
        headers=auth_headers(token),
    )
    assert b.status_code == 201, b.text

    r1 = await client.get(_notes_url(cid), headers=auth_headers(token))
    assert r1.status_code == 200, r1.text
    items = r1.json()["items"]
    assert [n["body"] for n in items] == ["Refund issued", "Called about a refund"]
    # An omitted author is null, not an error.
    assert items[0]["author"] is None


async def test_notes_reject_blank_body(client):
    _, token, _ = await make_client_account(client)
    cid = await _make_customer(client, token)

    bad = await client.post(
        _notes_url(cid), json={"body": "   "}, headers=auth_headers(token)
    )
    assert bad.status_code == 400, bad.text


async def test_notes_are_owner_scoped(client):
    _, token_a, _ = await make_client_account(client)
    _, token_b, _ = await make_client_account(client)
    cid_a = await _make_customer(client, token_a, name="A-cust")

    await client.post(
        _notes_url(cid_a),
        json={"body": "A private note"},
        headers=auth_headers(token_a),
    )

    # Tenant B cannot read tenant A's customer's notes — foreign id 404s.
    rb = await client.get(_notes_url(cid_a), headers=auth_headers(token_b))
    assert rb.status_code == 404, rb.text

    # Tenant B cannot append to tenant A's customer either.
    pb = await client.post(
        _notes_url(cid_a), json={"body": "intrusion"}, headers=auth_headers(token_b)
    )
    assert pb.status_code == 404, pb.text

    # Tenant A still sees exactly their one note (nothing leaked in).
    ra = await client.get(_notes_url(cid_a), headers=auth_headers(token_a))
    assert ra.status_code == 200, ra.text
    assert [n["body"] for n in ra.json()["items"]] == ["A private note"]
