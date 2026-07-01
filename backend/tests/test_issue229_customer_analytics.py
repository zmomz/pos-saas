"""Issue #229 (M9·Analytics) — CLV + repeat-rate tracer bullet.

The first end-to-end slice of the advanced-analytics epic. Where the M9
financial reports answer "how much did we take" and the #228 forecasts answer
"what will we sell", this answers "who are our customers and what are they
worth": it groups the tenant's sales by customer (keyed on ``customer_phone``,
the only stable buyer identity a transaction carries) and derives, per customer,
a lifetime value (net revenue — credit notes subtract) and an order count, then
rolls those up into the two headline analytics numbers the acceptance calls for:
average CLV and repeat-purchase rate.

Cohort tables, funnels, peak-hour heatmaps remain for later slices; this proves
the pipe reaches through every layer (Transactions → SQL group-by → schema →
router) and stays honest about tenancy, refund netting, and held/voided/anonymous
exclusion:

* per-customer CLV and order count, with repeat flag on order_count >= 2;
* the aggregate repeat_rate and average_clv render correctly;
* credit notes net against a customer's lifetime value;
* held/voided tickets and anonymous (no-phone) sales are excluded;
* one tenant's customers never leak into another's analytics.
"""
from datetime import datetime, timezone, timedelta

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.transactions import Transactions


async def _seed_sale(
    client_id,
    user_id,
    days_ago,
    total,
    *,
    phone,
    name=None,
    status="completed",
    idx=0,
):
    """One transaction attributed to ``phone`` (the buyer identity)."""
    created = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=1)
    async with db_manager.async_session_maker() as db:
        db.add(
            Transactions(
                user_id=user_id,
                client_id=client_id,
                invoice_number=f"INV-CA-{client_id}-{status}-{days_ago}-{idx}",
                subtotal=total,
                vat_amount=0.0,
                discount_amount=0.0,
                total_amount=total,
                payment_method="cash",
                status=status,
                customer_phone=phone,
                customer_name=name,
                created_at=created,
            )
        )
        await db.commit()


async def test_clv_and_repeat_flag_per_customer(client):
    """A two-order customer is repeat with CLV = the sum of their orders."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Alice: two orders → repeat, CLV 30. Bob: one order → not repeat, CLV 50.
    await _seed_sale(client_id, user["id"], 5, 10.0, phone="0500000001", name="Alice", idx=0)
    await _seed_sale(client_id, user["id"], 2, 20.0, phone="0500000001", name="Alice", idx=1)
    await _seed_sale(client_id, user["id"], 3, 50.0, phone="0500000002", name="Bob", idx=0)

    resp = await client.get(
        "/api/v1/reports/customer-analytics?lookback=30", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["method"] == "clv_repeat_rate"
    assert body["lookback_days"] == 30
    assert body["total_customers"] == 2

    by_phone = {c["customer_phone"]: c for c in body["customers"]}
    alice = by_phone["0500000001"]
    assert alice["customer_name"] == "Alice"
    assert alice["order_count"] == 2
    assert abs(alice["lifetime_value"] - 30.0) < 0.001
    assert alice["is_repeat"] is True

    bob = by_phone["0500000002"]
    assert bob["order_count"] == 1
    assert abs(bob["lifetime_value"] - 50.0) < 0.001
    assert bob["is_repeat"] is False


async def test_aggregate_repeat_rate_and_average_clv(client):
    """The rollup: 1 of 2 customers is repeat → 0.5; average CLV = mean of CLVs."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed_sale(client_id, user["id"], 5, 10.0, phone="0500000001", idx=0)
    await _seed_sale(client_id, user["id"], 2, 20.0, phone="0500000001", idx=1)
    await _seed_sale(client_id, user["id"], 3, 50.0, phone="0500000002", idx=0)

    resp = await client.get(
        "/api/v1/reports/customer-analytics?lookback=30", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["repeat_customers"] == 1
    assert abs(body["repeat_rate"] - 0.5) < 0.001
    # CLVs 30 and 50 → mean 40; total revenue 80.
    assert abs(body["average_clv"] - 40.0) < 0.001
    assert abs(body["total_revenue"] - 80.0) < 0.001


async def test_credit_note_nets_against_lifetime_value(client):
    """A refund (credit note) subtracts from the customer's CLV."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Two purchases (10 + 20 = 30), then a 5.00 credit note → CLV 25, but the
    # credit note is not a new *order*, so order_count stays at 2.
    await _seed_sale(client_id, user["id"], 5, 10.0, phone="0500000001", idx=0)
    await _seed_sale(client_id, user["id"], 3, 20.0, phone="0500000001", idx=1)
    await _seed_sale(
        client_id, user["id"], 2, 5.0, phone="0500000001", status="credit_note", idx=2
    )

    resp = await client.get(
        "/api/v1/reports/customer-analytics?lookback=30", headers=headers
    )
    assert resp.status_code == 200, resp.text
    cust = resp.json()["customers"][0]
    assert abs(cust["lifetime_value"] - 25.0) < 0.001
    assert cust["order_count"] == 2


async def test_held_voided_and_anonymous_sales_excluded(client):
    """Held/voided tickets and no-phone (walk-in) sales are not customer revenue."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed_sale(client_id, user["id"], 2, 10.0, phone="0500000001", idx=0)
    await _seed_sale(
        client_id, user["id"], 2, 99.0, phone="0500000001", status="held", idx=1
    )
    await _seed_sale(
        client_id, user["id"], 2, 99.0, phone="0500000001", status="voided", idx=2
    )
    # Anonymous walk-ins carry no phone and cannot be attributed to a customer.
    await _seed_sale(client_id, user["id"], 2, 77.0, phone="", idx=3)
    await _seed_sale(client_id, user["id"], 2, 77.0, phone=None, idx=4)

    resp = await client.get(
        "/api/v1/reports/customer-analytics?lookback=30", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_customers"] == 1
    cust = body["customers"][0]
    assert cust["customer_phone"] == "0500000001"
    # Only the single 10.00 completed sale counts.
    assert abs(cust["lifetime_value"] - 10.0) < 0.001
    assert cust["order_count"] == 1


async def test_customer_analytics_is_tenant_scoped(client):
    """One tenant's customers never leak into another tenant's analytics."""
    user_a, token_a, client_a = await make_client_account(client)
    user_b, token_b, client_b = await make_client_account(client)

    await _seed_sale(client_b, user_b["id"], 2, 500.0, phone="0500009999", idx=0)

    resp = await client.get(
        "/api/v1/reports/customer-analytics?lookback=30",
        headers=auth_headers(token_a),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_customers"] == 0
    assert body["customers"] == []
    assert body["repeat_rate"] == 0.0
    assert body["average_clv"] == 0.0
