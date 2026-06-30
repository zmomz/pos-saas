"""M5·CRM (#221) — per-customer purchase timeline (tracer bullet).

Scope item: "notes, purchase timeline". A merchant opens a customer and sees their
purchase history as a chronological timeline — each settled sale and each refund
(credit note) as an event, newest-first, with a summary (how many purchases, net
total spent, first/last purchase). Transactions carry no customer FK, so events are
matched by the PII denormalized onto the sale (phone, then name) — the same join the
PDPL export and the RFM insights endpoint use.

The server is authoritative and owner-scoped (SEC-02): a foreign/unknown customer id
→ 404, and another tenant's sales never bleed into the timeline. Voided/held rows are
not purchases and are excluded; credit notes appear as refund events and net out of
the total spent.
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


async def _make_customer(client, token, name="Timeline Cust", phone=None):
    body = {"name": name}
    if phone:
        body["phone"] = phone
    resp = await client.post(
        "/api/v1/entities/customers", json=body, headers=auth_headers(token)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_timeline_lists_settled_sales_newest_first_with_summary(client):
    """A customer with no sales has an empty timeline; once they buy, every settled
    sale shows up as an event newest-first with a purchase_count / total_spent /
    first+last summary."""
    user, token, client_id = await make_client_account(client)
    phone = "+966500000010"
    cust_id = await _make_customer(client, token, phone=phone)

    # No purchases yet → empty timeline, zeroed summary.
    r0 = await client.get(
        f"/api/v1/entities/customers/{cust_id}/timeline", headers=auth_headers(token)
    )
    assert r0.status_code == 200, r0.text
    b0 = r0.json()
    assert b0["events"] == []
    assert b0["purchase_count"] == 0
    assert b0["total_spent"] == 0.0
    assert b0["first_purchase_at"] is None
    assert b0["last_purchase_at"] is None

    await _seed_txn(client_id, user["id"], phone, 100.0, "completed", days_ago=5)
    await _seed_txn(client_id, user["id"], phone, 300.0, "completed", days_ago=1)

    r1 = await client.get(
        f"/api/v1/entities/customers/{cust_id}/timeline", headers=auth_headers(token)
    )
    assert r1.status_code == 200, r1.text
    b1 = r1.json()
    assert b1["purchase_count"] == 2
    assert b1["total_spent"] == 400.0
    # Newest-first: the 1-day-ago 300.0 sale leads.
    assert [e["total_amount"] for e in b1["events"]] == [300.0, 100.0]
    assert all(e["kind"] == "sale" for e in b1["events"])
    assert b1["events"][0]["invoice_number"]
    # first/last bracket the two sales (last is the most recent).
    assert b1["first_purchase_at"] is not None
    assert b1["last_purchase_at"] is not None
    assert b1["last_purchase_at"] > b1["first_purchase_at"]


async def test_refunds_appear_as_events_and_net_out_voids_excluded(client):
    """Credit notes appear as refund events and net out of total_spent; voided/held
    rows are not purchases and never appear."""
    user, token, client_id = await make_client_account(client)
    phone = "+966500000011"
    cust_id = await _make_customer(client, token, phone=phone)

    await _seed_txn(client_id, user["id"], phone, 200.0, "completed", days_ago=4)
    await _seed_txn(client_id, user["id"], phone, 50.0, "credit_note", days_ago=2)  # refund
    await _seed_txn(client_id, user["id"], phone, 999.0, "voided", days_ago=3)       # not a sale
    await _seed_txn(client_id, user["id"], phone, 888.0, "held", days_ago=1)         # parked

    r = await client.get(
        f"/api/v1/entities/customers/{cust_id}/timeline", headers=auth_headers(token)
    )
    assert r.status_code == 200, r.text
    b = r.json()

    # Only the sale and the refund are timeline events; void/held excluded.
    kinds = [e["kind"] for e in b["events"]]
    assert sorted(kinds) == ["refund", "sale"]
    assert 999.0 not in [e["total_amount"] for e in b["events"]]
    assert 888.0 not in [e["total_amount"] for e in b["events"]]

    # purchase_count counts settled sales only; total_spent nets the refund.
    assert b["purchase_count"] == 1
    assert b["total_spent"] == 150.0


async def test_timeline_is_owner_scoped(client):
    """A foreign/unknown customer id → 404, and another tenant's sales never bleed in."""
    user_a, token_a, client_a = await make_client_account(client)
    user_b, token_b, client_b = await make_client_account(client)

    phone = "+966500000012"
    cust_a = await _make_customer(client, token_a, name="Shared Name", phone=phone)
    # Tenant B's sale shares the same phone+name but belongs to B.
    await _seed_txn(client_b, user_b["id"], phone, 700.0, "completed", days_ago=1, name="Shared Name")
    # Tenant A's own sale.
    await _seed_txn(client_a, user_a["id"], phone, 120.0, "completed", days_ago=1, name="Shared Name")

    # A only sees A's sale, never B's 700.0.
    r = await client.get(
        f"/api/v1/entities/customers/{cust_a}/timeline", headers=auth_headers(token_a)
    )
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["total_spent"] == 120.0
    assert 700.0 not in [e["total_amount"] for e in b["events"]]

    # B cannot read A's customer timeline at all → 404.
    r404 = await client.get(
        f"/api/v1/entities/customers/{cust_a}/timeline", headers=auth_headers(token_b)
    )
    assert r404.status_code == 404, r404.text
