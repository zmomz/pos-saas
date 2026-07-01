"""Issue #228 (M9·AI) — in-app assistant tracer bullet.

The forecasting / smart-reorder / dynamic-pricing slices of #228 each answer a
single fixed question. The *assistant* is the conversational surface over the
same tenant data: the operator types a plain question and gets a grounded
answer computed from their own transactions and catalogue — no external LLM key
required for this first slice. ``method`` names the model (``rule_based`` today;
an LLM-backed router later) so the response is self-describing as it grows, and
``intent`` exposes how the question was routed so the surface is inspectable.

Every answer is tenant-scoped and client-only, exactly like the sibling
``/reports/*`` endpoints. Unroutable questions degrade to a helpful capability
list (HTTP 200), never a 400/500.
"""
from datetime import datetime, timezone, timedelta

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.products import Products
from models.transactions import Transactions


async def _seed_sale(client_id: int, user_id: str, *, days_ago: float, total: float,
                     items, status: str = "completed", idx: int = 0):
    """Insert one transaction carrying ``items`` (list of {product_id, quantity})."""
    import json as _json

    created = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=1)
    async with db_manager.async_session_maker() as db:
        db.add(
            Transactions(
                user_id=user_id,
                client_id=client_id,
                invoice_number=f"INV-AS-{client_id}-{status}-{idx}",
                subtotal=total,
                vat_amount=0.0,
                discount_amount=0.0,
                total_amount=total,
                payment_method="cash",
                status=status,
                items_json=_json.dumps(items),
                created_at=created,
            )
        )
        await db.commit()


async def _seed_product(client_id: int, user_id: str, *, name: str, quantity: float,
                        reorder_point: int = 0, is_digital: bool = False) -> int:
    async with db_manager.async_session_maker() as db:
        p = Products(
            user_id=user_id,
            client_id=client_id,
            name=name,
            price=10.0,
            quantity=quantity,
            reorder_point=reorder_point,
            is_active=True,
            is_digital=is_digital,
        )
        db.add(p)
        await db.commit()
        await db.refresh(p)
        return p.id


async def test_assistant_names_the_top_selling_product(client):
    """"What's my best seller?" → the product with the most units sold."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    latte = await _seed_product(client_id, user["id"], name="Latte", quantity=50)
    muffin = await _seed_product(client_id, user["id"], name="Muffin", quantity=50)

    # Muffin outsells Latte over the window (12 units vs 5).
    await _seed_sale(client_id, user["id"], days_ago=1, total=100.0,
                     items=[{"product_id": latte, "quantity": 5}], idx=1)
    await _seed_sale(client_id, user["id"], days_ago=2, total=120.0,
                     items=[{"product_id": muffin, "quantity": 12}], idx=2)

    resp = await client.get(
        "/api/v1/assistant/query?q=what is my best selling product",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["method"] == "rule_based"
    assert body["intent"] == "top_product"
    assert body["data"]["product_id"] == muffin
    assert body["data"]["units_sold"] == 12
    assert "Muffin" in body["answer"]


async def test_assistant_reports_todays_net_sales(client):
    """"How much did I sell today?" → today's net takings; a credit note nets out."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Two sales today (300 + 200) and a credit note today (−50) → net 450.
    await _seed_sale(client_id, user["id"], days_ago=0, total=300.0, items=[], idx=1)
    await _seed_sale(client_id, user["id"], days_ago=0, total=200.0, items=[], idx=2)
    await _seed_sale(client_id, user["id"], days_ago=0, total=50.0, items=[],
                     status="credit_note", idx=3)
    # A sale a week ago must NOT count toward "today".
    await _seed_sale(client_id, user["id"], days_ago=7, total=999.0, items=[], idx=4)

    resp = await client.get(
        "/api/v1/assistant/query?q=how much did I sell today", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "sales_today"
    assert abs(body["data"]["net_sales"] - 450.0) < 0.01
    assert body["data"]["order_count"] == 2


async def test_assistant_lists_low_stock_products(client):
    """"Which products are low on stock?" → the reorder-point-aware low list."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Below its reorder point → low; well-stocked → not; digital → never low.
    await _seed_product(client_id, user["id"], name="Beans", quantity=2, reorder_point=10)
    await _seed_product(client_id, user["id"], name="Cups", quantity=500, reorder_point=10)
    await _seed_product(client_id, user["id"], name="Gift Card", quantity=0,
                        reorder_point=10, is_digital=True)

    resp = await client.get(
        "/api/v1/assistant/query?q=which products are low on stock", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "low_stock"
    assert body["data"]["count"] == 1
    names = [p["name"] for p in body["data"]["products"]]
    assert names == ["Beans"]
    assert "Beans" in body["answer"]


async def test_assistant_unroutable_question_degrades_gracefully(client):
    """A question it can't map is an ``unknown`` answer with suggestions, not a 400/500."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    resp = await client.get(
        "/api/v1/assistant/query?q=what is the meaning of life", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "unknown"
    # It still offers a way forward: the capability list is populated.
    assert len(body["suggestions"]) >= 3


async def test_assistant_is_tenant_scoped(client):
    """One tenant's assistant never sees another tenant's sales."""
    user_a, token_a, client_a = await make_client_account(client)
    user_b, token_b, client_b = await make_client_account(client)

    # Tenant B has a runaway best-seller; tenant A has nothing.
    widget = await _seed_product(client_b, user_b["id"], name="Widget", quantity=50)
    await _seed_sale(client_b, user_b["id"], days_ago=1, total=500.0,
                     items=[{"product_id": widget, "quantity": 99}], idx=1)

    resp = await client.get(
        "/api/v1/assistant/query?q=what is my best selling product",
        headers=auth_headers(token_a),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["intent"] == "top_product"
    # Tenant A has no sales — B's Widget must not leak across the tenant boundary.
    assert body["data"] == {}
    assert "Widget" not in body["answer"]


async def test_assistant_rejects_non_clients(client):
    """A master (non-client) account cannot reach the assistant (403), like reports."""
    from conftest import make_master_account

    _user, token = await make_master_account(client)
    resp = await client.get(
        "/api/v1/assistant/query?q=what is my best selling product",
        headers=auth_headers(token),
    )
    assert resp.status_code == 403, resp.text
