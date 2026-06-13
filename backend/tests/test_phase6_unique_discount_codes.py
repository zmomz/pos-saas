"""ISSUE-059 — single-use / unique discount codes (PRC, P2 pricing).

Distinct from the reusable ``Discounts`` definitions (one shared code, a usage
cap counted up across many sales), a *unique* discount code is minted in a batch,
each member redeemable **exactly once** within its validity window. The server is
the single source of truth: it generates the codes, prices the discount, and
consumes the one-and-only use atomically so a second redemption — or a redemption
outside the window — is rejected.

Catches forever (per ISSUE-059 acceptance):
* a batch generates N distinct codes;
* a freshly minted code redeems once and returns the server-priced amount;
* the SAME code redeemed a second time is rejected (one-shot);
* a code redeemed outside its validity window (not-yet-active / expired) is rejected;
* codes are owner-scoped (another tenant cannot redeem mine).
"""
from conftest import auth_headers, make_client_account


async def _generate(client, headers, **fields):
    payload = {"count": 3, "type": "percentage", "value": 10.0}
    payload.update(fields)
    resp = await client.post(
        "/api/v1/entities/discount-codes/generate", json=payload, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# A batch mints N distinct, redeemable codes.
# ---------------------------------------------------------------------------
async def test_generate_batch_mints_distinct_codes(client):
    _, token, _ = await make_client_account(client)
    headers = auth_headers(token)

    body = await _generate(client, headers, count=5, type="percentage", value=15.0)

    codes = [c["code"] for c in body["codes"]]
    assert len(codes) == 5
    assert len(set(codes)) == 5  # every minted code is unique
    assert body["count"] == 5
    assert all(c["type"] == "percentage" and c["value"] == 15.0 for c in body["codes"])


async def _redeem(client, headers, code, subtotal):
    return await client.post(
        "/api/v1/entities/discount-codes/redeem",
        json={"code": code, "subtotal": subtotal},
        headers=headers,
    )


# ---------------------------------------------------------------------------
# A freshly minted code redeems once, priced server-side.
# ---------------------------------------------------------------------------
async def test_code_redeems_once_priced_server_side(client):
    _, token, _ = await make_client_account(client)
    headers = auth_headers(token)
    body = await _generate(client, headers, count=1, type="percentage", value=10.0)
    code = body["codes"][0]["code"]

    resp = await _redeem(client, headers, code, 100.0)
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["valid"] is True
    assert out["code"] == code
    # 10% of a 100 subtotal, priced from the rule (never client-trusted).
    assert abs(out["discount_amount"] - 10.0) < 0.01


# ---------------------------------------------------------------------------
# One-shot: the SAME code redeemed a second time is rejected.
# ---------------------------------------------------------------------------
async def test_second_redemption_is_rejected(client):
    _, token, _ = await make_client_account(client)
    headers = auth_headers(token)
    body = await _generate(client, headers, count=1, type="fixed", value=5.0)
    code = body["codes"][0]["code"]

    first = await _redeem(client, headers, code, 100.0)
    assert first.status_code == 200, first.text

    second = await _redeem(client, headers, code, 100.0)
    assert second.status_code == 400, second.text
    assert "redeemed" in second.json()["detail"].lower()


# Fixed far-apart bounds make the window unambiguous regardless of the wall clock.
FAR_PAST = "2000-01-01T00:00:00"
FAR_FUTURE = "2999-01-01T00:00:00"


# ---------------------------------------------------------------------------
# A code outside its validity window is rejected at apply time (and not consumed).
# ---------------------------------------------------------------------------
async def test_expired_code_is_rejected(client):
    _, token, _ = await make_client_account(client)
    headers = auth_headers(token)
    body = await _generate(
        client, headers, count=1, starts_at=FAR_PAST, ends_at=FAR_PAST
    )
    code = body["codes"][0]["code"]

    resp = await _redeem(client, headers, code, 100.0)
    assert resp.status_code == 400, resp.text
    assert "expired" in resp.json()["detail"].lower()


async def test_not_yet_active_code_is_rejected(client):
    _, token, _ = await make_client_account(client)
    headers = auth_headers(token)
    body = await _generate(
        client, headers, count=1, starts_at=FAR_FUTURE, ends_at=FAR_FUTURE
    )
    code = body["codes"][0]["code"]

    resp = await _redeem(client, headers, code, 100.0)
    assert resp.status_code == 400, resp.text
    assert "not active yet" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Owner-scoping (SEC-02): another tenant cannot redeem my code.
# ---------------------------------------------------------------------------
async def test_codes_are_owner_scoped(client):
    _, owner_token, _ = await make_client_account(client)
    owner_headers = auth_headers(owner_token)
    body = await _generate(client, owner_headers, count=1, value=10.0)
    code = body["codes"][0]["code"]

    _, other_token, _ = await make_client_account(client)
    other_headers = auth_headers(other_token)

    # The other tenant cannot redeem a code that isn't theirs.
    stolen = await _redeem(client, other_headers, code, 100.0)
    assert stolen.status_code == 400, stolen.text

    # ...and the owner can still redeem it (it was not consumed by the attempt).
    ok = await _redeem(client, owner_headers, code, 100.0)
    assert ok.status_code == 200, ok.text
