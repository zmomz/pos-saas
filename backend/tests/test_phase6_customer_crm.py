"""Phase 6 — customer segmentation tags + computed LTV/RFM insights
(F-039 first slice / CRM-04, P1).

CRM-04 asks for *"segments/tags + RFM-lite"*. This slice adds:

* a free-form ``tags`` list on the customer (segmentation labels), round-tripped
  through the generic customers triad as a real JSON array (trimmed + deduped);
* a computed ``GET /insights`` endpoint — lifetime value **net of refunds**,
  visit frequency, recency and an RFM-lite segment — aggregated in SQL from the
  fiscal rows linked to the customer by phone (there is no customer FK on
  ``transactions``; the PDPL export uses the same join).

These tests pin the behaviour so it stays caught forever: tags persist + clear;
the lifetime value nets a credit-note refund and counts only settled visits; the
endpoint is owner-scoped (SEC-02 — one client never reads another's customer).
"""
from datetime import datetime, timezone, timedelta

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.transactions import Transactions


async def _seed_txn(client_id, user_id, phone, total, status, days_ago, name=None):
    """Insert one fiscal row linked to a customer by phone (deterministic)."""
    async with db_manager.async_session_maker() as db:
        db.add(
            Transactions(
                user_id=user_id,
                client_id=client_id,
                invoice_number=f"INV-{client_id:04d}-{days_ago:03d}-{int(total)}-{status}",
                subtotal=total,
                vat_amount=0.0,
                total_amount=total,
                payment_method="cash",
                status=status,
                customer_phone=phone,
                customer_name=name,
                created_at=datetime.now(timezone.utc) - timedelta(days=days_ago, hours=1),
            )
        )
        await db.commit()


async def test_customer_insights_computes_ltv_frequency_and_nets_refunds(client):
    """CRM-04: LTV = gross settled sales − refunds; voided/held/credit-note rows
    are not counted as visits, and another customer's sales don't bleed in."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    phone = "+966500000001"
    resp = await client.post(
        "/api/v1/entities/customers",
        headers=headers,
        json={"name": "Layla", "phone": phone},
    )
    assert resp.status_code == 201, resp.text
    cust_id = resp.json()["id"]

    await _seed_txn(client_id, user["id"], phone, 100.0, "completed", days_ago=2)
    await _seed_txn(client_id, user["id"], phone, 300.0, "completed", days_ago=10)
    await _seed_txn(client_id, user["id"], phone, 50.0, "credit_note", days_ago=1)  # refund
    await _seed_txn(client_id, user["id"], phone, 999.0, "voided", days_ago=3)       # not a sale
    # A different customer's sale (same merchant) must never bleed in.
    await _seed_txn(client_id, user["id"], "+966500000999", 777.0, "completed", days_ago=1)

    r = await client.get(f"/api/v1/entities/customers/{cust_id}/insights", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["gross_sales"] == 400.0       # 100 + 300 (voided excluded)
    assert body["refunds"] == 50.0            # the credit note
    assert body["lifetime_value"] == 350.0    # 400 - 50, net
    assert body["visit_count"] == 2           # only settled sales count as visits
    assert body["average_basket"] == 200.0    # 400 / 2
    assert body["recency_days"] is not None and body["recency_days"] <= 11
    assert body["segment"] == "regular"       # recent, <5 visits, <5000 SAR


async def test_customer_insights_segments_lapsed_buyer_as_at_risk(client):
    """RFM-lite: a buyer whose last settled sale is >90 days old is ``at_risk``."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    phone = "+966500000777"
    resp = await client.post(
        "/api/v1/entities/customers",
        headers=headers,
        json={"name": "Dormant", "phone": phone},
    )
    cust_id = resp.json()["id"]
    await _seed_txn(client_id, user["id"], phone, 250.0, "completed", days_ago=200)

    r = await client.get(f"/api/v1/entities/customers/{cust_id}/insights", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["visit_count"] == 1
    assert body["lifetime_value"] == 250.0
    assert body["segment"] == "at_risk"

    # A brand-new customer with no sales is ``new`` with zeroed metrics.
    fresh = await client.post(
        "/api/v1/entities/customers", headers=headers, json={"name": "Newbie"}
    )
    fresh_id = fresh.json()["id"]
    rf = await client.get(f"/api/v1/entities/customers/{fresh_id}/insights", headers=headers)
    assert rf.status_code == 200, rf.text
    fb = rf.json()
    assert fb["visit_count"] == 0
    assert fb["lifetime_value"] == 0.0
    assert fb["segment"] == "new"


async def test_customer_tags_persist_round_trip_and_clear(client):
    """CRM-04: tags are stored + returned as a real array (trimmed/deduped); an
    update replaces them and an empty list clears them."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    resp = await client.post(
        "/api/v1/entities/customers",
        headers=headers,
        json={"name": "Omar", "phone": "+966500000002", "tags": ["VIP", "wholesale", " vip "]},
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()
    # Case-insensitive dedup + trim, original order preserved.
    assert created["tags"] == ["VIP", "wholesale"]
    cust_id = created["id"]

    got = await client.get(f"/api/v1/entities/customers/{cust_id}", headers=headers)
    assert got.json()["tags"] == ["VIP", "wholesale"]

    upd = await client.put(
        f"/api/v1/entities/customers/{cust_id}", headers=headers, json={"tags": ["regular"]}
    )
    assert upd.status_code == 200, upd.text
    assert upd.json()["tags"] == ["regular"]

    cleared = await client.put(
        f"/api/v1/entities/customers/{cust_id}", headers=headers, json={"tags": []}
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["tags"] is None


async def test_customer_insights_is_owner_scoped(client):
    """SEC-02: one client cannot read another client's customer insights."""
    user_a, token_a, _ = await make_client_account(client)
    _user_b, token_b, _ = await make_client_account(client)

    resp = await client.post(
        "/api/v1/entities/customers",
        headers=auth_headers(token_a),
        json={"name": "A-cust", "phone": "+966511111111"},
    )
    cust_id = resp.json()["id"]

    # Client B requests A's customer → 404 (scoped by owner_user_id).
    r = await client.get(
        f"/api/v1/entities/customers/{cust_id}/insights", headers=auth_headers(token_b)
    )
    assert r.status_code == 404, r.text
