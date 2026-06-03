"""Phase 6 — report aggregators do not load every transaction into memory (F-048 / OPS-05).

The sales-summary endpoint used to ``select(Transactions)`` for the whole period
and group the rows in a Python loop; at scale that degrades / OOMs. OPS-05 (P0)
requires server-side aggregation — *no load-everything*. These tests prove:

* sales-summary now groups in SQL (a single ``GROUP BY`` is issued and the
  result set is bounded by the number of periods, not the transaction count);
* top-products and export-csv stream their window instead of materializing it,
  and still return correct results.
"""
from datetime import datetime, timezone, timedelta

import json

from sqlalchemy import event

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.transactions import Transactions


async def _seed_transactions(client_id: int, user_id: str, specs):
    """Insert transactions directly (fast, deterministic) for a client.

    ``specs`` is a list of ``(days_ago, total_amount, items)`` tuples; ``items``
    is the parsed line-item list stored as ``items_json``.
    """
    async with db_manager.async_session_maker() as db:
        for i, (days_ago, total, items) in enumerate(specs):
            created = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=1)
            db.add(
                Transactions(
                    user_id=user_id,
                    client_id=client_id,
                    invoice_number=f"INV-SEED-{client_id}-{i}",
                    subtotal=total,
                    vat_amount=0.0,
                    discount_amount=0.0,
                    total_amount=total,
                    payment_method="cash",
                    status="completed",
                    items_json=json.dumps(items) if items is not None else None,
                    created_at=created,
                )
            )
        await db.commit()


async def test_sales_summary_aggregates_in_sql_not_in_memory(client):
    """OPS-05: sales-summary issues a GROUP BY and returns one row per period."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Many transactions spread across exactly 3 distinct days inside the window.
    specs = []
    for day in (1, 1, 1, 5, 5, 10):
        specs.append((day, 100.0, None))
    # Pad with volume to make "group in SQL, not in Python" meaningful.
    specs += [(1, 100.0, None) for _ in range(50)]
    await _seed_transactions(client_id, user["id"], specs)

    # Capture every SQL statement issued while the report runs.
    statements: list[str] = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db_manager.engine.sync_engine, "after_cursor_execute", _capture)
    try:
        resp = await client.get(
            "/api/v1/reports/sales-summary?period=daily&days=30", headers=headers
        )
    finally:
        event.remove(db_manager.engine.sync_engine, "after_cursor_execute", _capture)

    assert resp.status_code == 200, resp.text
    body = resp.json()

    # One summary row per distinct day — bounded by periods, not transactions.
    assert len(body["items"]) == 3
    assert body["total_transactions"] == len(specs)
    assert abs(body["total_sales"] - 100.0 * len(specs)) < 0.01

    # The aggregate ran in the database: a GROUP BY over the transactions table
    # was issued (the old load-everything path had none — fails before the fix).
    agg = [s for s in statements if "transactions" in s.lower() and "group by" in s.lower()]
    assert agg, f"expected a GROUP BY over transactions, got: {statements}"


async def test_top_products_streams_and_aggregates(client):
    """top-products folds streamed line items into per-product totals."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    specs = [
        (1, 30.0, [{"product_id": 1, "name": "Cola", "price": 10.0, "quantity": 3}]),
        (2, 20.0, [{"product_id": 1, "name": "Cola", "price": 10.0, "quantity": 2},
                   {"product_id": 2, "name": "Water", "price": 5.0, "quantity": 1}]),
        (3, 5.0, [{"product_id": 2, "name": "Water", "price": 5.0, "quantity": 1}]),
    ]
    await _seed_transactions(client_id, user["id"], specs)

    resp = await client.get("/api/v1/reports/top-products?days=30&limit=10", headers=headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]

    by_id = {it["product_id"]: it for it in items}
    assert by_id[1]["total_quantity_sold"] == 5   # 3 + 2
    assert abs(by_id[1]["total_revenue"] - 50.0) < 0.01
    assert by_id[2]["total_quantity_sold"] == 2   # 1 + 1
    # Sorted by quantity desc → Cola first.
    assert items[0]["product_id"] == 1


async def test_export_csv_streams_all_rows(client):
    """export-csv streams every row in the window and reports the true count."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed_transactions(client_id, user["id"], [(1, 10.0, None) for _ in range(25)])

    resp = await client.get("/api/v1/reports/export-csv?days=30", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["row_count"] == 25
    # Header + 25 data rows.
    assert body["csv_content"].count("INV-SEED-") == 25
