"""M5·CRM (#221) — birthday rewards (tracer bullet).

Scope item: "birthday rewards". A merchant runs a birthday-reward batch for a given
day: every customer whose date of birth falls on that month/day is granted a fixed
amount of store credit (a goodwill loyalty payout), booked onto their store-credit
ledger as a ``grant`` so it accrues and can later be spent like any other credit.

The server is authoritative and owner-scoped (SEC-02): a run only ever touches the
caller's own customers, never another tenant's. It is idempotent per birthday year —
re-running the same day does not double-grant — and skips blacklisted / erased
customers (they are not in good standing / have no usable identity to reward).
"""
from conftest import auth_headers, make_client_account

_RUN_URL = "/api/v1/entities/customers/birthday-rewards"


async def _make_customer(client, token, name, dob=None):
    body = {"name": name}
    if dob is not None:
        body["date_of_birth"] = dob
    resp = await client.post(
        "/api/v1/entities/customers", json=body, headers=auth_headers(token)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _balance(client, token, cid):
    r = await client.get(
        f"/api/v1/entities/customers/{cid}/store-credit", headers=auth_headers(token)
    )
    assert r.status_code == 200, r.text
    return r.json()["balance"]


async def test_birthday_run_grants_credit_only_to_matching_customers(client):
    _, token, _ = await make_client_account(client)
    # Two customers share the run day (different years); one is on another day; one
    # has no DOB at all.
    a = await _make_customer(client, token, "Aliyah", dob="1990-06-30")
    b = await _make_customer(client, token, "Basim", dob="1985-06-30")
    c = await _make_customer(client, token, "Carla", dob="1990-07-01")
    d = await _make_customer(client, token, "Dana")  # no DOB

    resp = await client.post(
        _RUN_URL,
        json={"amount": 25, "on_date": "2026-06-30"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["amount"] == 25
    assert payload["count"] == 2
    rewarded_ids = {row["customer_id"] for row in payload["rewarded"]}
    assert rewarded_ids == {a["id"], b["id"]}

    # The matching customers carry the credit; the others do not.
    assert await _balance(client, token, a["id"]) == 25
    assert await _balance(client, token, b["id"]) == 25
    assert await _balance(client, token, c["id"]) == 0
    assert await _balance(client, token, d["id"]) == 0

    # The credit shows up as a ``grant`` on the ledger (auditable accrual).
    hist = await client.get(
        f"/api/v1/entities/customers/{a['id']}/store-credit",
        headers=auth_headers(token),
    )
    entries = hist.json()["history"]
    assert len(entries) == 1
    assert entries[0]["entry_type"] == "grant"
    assert entries[0]["amount"] == 25


async def test_birthday_run_is_idempotent_per_year(client):
    _, token, _ = await make_client_account(client)
    cust = await _make_customer(client, token, "Repeat", dob="1992-06-30")

    first = await client.post(
        _RUN_URL,
        json={"amount": 10, "on_date": "2026-06-30"},
        headers=auth_headers(token),
    )
    assert first.status_code == 200, first.text
    assert first.json()["count"] == 1

    # Re-running the same birthday day grants nothing more — no double credit.
    again = await client.post(
        _RUN_URL,
        json={"amount": 10, "on_date": "2026-06-30"},
        headers=auth_headers(token),
    )
    assert again.status_code == 200, again.text
    assert again.json()["count"] == 0
    assert again.json()["rewarded"] == []

    # The balance reflects exactly one grant, and the ledger has a single row.
    assert await _balance(client, token, cust["id"]) == 10
    hist = await client.get(
        f"/api/v1/entities/customers/{cust['id']}/store-credit",
        headers=auth_headers(token),
    )
    assert len(hist.json()["history"]) == 1

    # A *different* year is a distinct birthday occurrence — it rewards again.
    next_year = await client.post(
        _RUN_URL,
        json={"amount": 10, "on_date": "2027-06-30"},
        headers=auth_headers(token),
    )
    assert next_year.status_code == 200, next_year.text
    assert next_year.json()["count"] == 1
    assert await _balance(client, token, cust["id"]) == 20


async def test_birthday_run_rejects_non_positive_amount(client):
    _, token, _ = await make_client_account(client)
    await _make_customer(client, token, "Anyone", dob="1992-06-30")

    bad = await client.post(
        _RUN_URL,
        json={"amount": 0, "on_date": "2026-06-30"},
        headers=auth_headers(token),
    )
    assert bad.status_code == 400, bad.text


async def test_birthday_run_is_owner_scoped_and_skips_ineligible(client):
    _, token_a, _ = await make_client_account(client)
    _, token_b, _ = await make_client_account(client)

    # Tenant A: one plain birthday customer, one blacklisted, one erased — all on
    # the same birthday. Tenant B has a birthday customer on the same day too.
    good = await _make_customer(client, token_a, "Good", dob="1990-06-30")
    barred = await _make_customer(client, token_a, "Barred", dob="1990-06-30")
    erased = await _make_customer(client, token_a, "Erased", dob="1990-06-30")
    b_cust = await _make_customer(client, token_b, "Tenant B", dob="1990-06-30")

    # Blacklist one of A's customers; erase another (PDPL right-to-erasure).
    bl = await client.post(
        f"/api/v1/entities/customers/{barred['id']}/blacklist",
        json={"reason": "fraud"},
        headers=auth_headers(token_a),
    )
    assert bl.status_code == 200, bl.text
    er = await client.post(
        f"/api/v1/entities/customers/{erased['id']}/erase",
        headers=auth_headers(token_a),
    )
    assert er.status_code == 200, er.text

    resp = await client.post(
        _RUN_URL,
        json={"amount": 15, "on_date": "2026-06-30"},
        headers=auth_headers(token_a),
    )
    assert resp.status_code == 200, resp.text
    # Only the in-good-standing customer with a usable identity is rewarded.
    assert {r["customer_id"] for r in resp.json()["rewarded"]} == {good["id"]}

    assert await _balance(client, token_a, good["id"]) == 15
    assert await _balance(client, token_a, barred["id"]) == 0
    assert await _balance(client, token_a, erased["id"]) == 0

    # Tenant B's matching customer was never touched by tenant A's run.
    assert await _balance(client, token_b, b_cust["id"]) == 0
