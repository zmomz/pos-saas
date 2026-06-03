"""Phase 6 — payment-method breakdown report (F-042 first slice / RPT-03, P0).

RPT-03 is a P0 table-stake: *"Payment-method breakdown (cash/Mada/card/wallet/
BNPL/loyalty) per period."* It is built from the **real captured ``payment_tenders``
rows** (F-001) — not a sum of ``payment_method`` labels — and nets refunds routed
back to origin (F-004) so ``net`` is what each method actually collected. These
tests prove:

* the endpoint groups a period's tenders by method and nets refunds;
* the aggregate runs in SQL (a single ``GROUP BY`` over ``payment_tenders`` —
  OPS-05, never load-everything);
* reports stay client-scoped (an agent is 403; one client never sees another's
  tenders).
"""
from datetime import datetime, timezone, timedelta

from sqlalchemy import event

from conftest import auth_headers, make_client_account, make_agent_account
from core.database import db_manager
from models.payment_tenders import PaymentTenders


async def _seed_tenders(client_id: int, user_id: str, specs):
    """Insert ``payment_tenders`` rows directly (fast, deterministic).

    ``specs`` is a list of ``(days_ago, tender_type, amount, status)`` tuples.
    """
    async with db_manager.async_session_maker() as db:
        for i, (days_ago, ttype, amount, status) in enumerate(specs):
            created = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=1)
            db.add(
                PaymentTenders(
                    user_id=user_id,
                    client_id=client_id,
                    transaction_id=1000 + i,
                    tender_type=ttype,
                    amount=amount,
                    status=status,
                    gateway="sandbox",
                    created_at=created,
                )
            )
        await db.commit()


async def test_payment_breakdown_groups_by_tender_with_refunds_netted(client):
    """RPT-03: per-method collected / refunds / net, plus period totals."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed_tenders(client_id, user["id"], [
        (1, "cash", 100.0, "captured"),
        (1, "cash", 50.0, "captured"),
        (2, "mada", 200.0, "captured"),
        (3, "mada", 30.0, "refunded"),     # money reversed back to Mada (F-004)
        (5, "card", 75.0, "captured"),
        (40, "cash", 999.0, "captured"),   # outside the 30-day window — excluded
    ])

    resp = await client.get("/api/v1/reports/payment-breakdown?days=30", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    by_type = {t["tender_type"]: t for t in body["tenders"]}
    assert set(by_type) == {"cash", "mada", "card"}

    assert by_type["cash"]["collected"] == 150.0
    assert by_type["cash"]["refunds"] == 0.0
    assert by_type["cash"]["net"] == 150.0
    assert by_type["cash"]["count"] == 2

    assert by_type["mada"]["collected"] == 200.0
    assert by_type["mada"]["refunds"] == 30.0
    assert by_type["mada"]["net"] == 170.0
    assert by_type["mada"]["count"] == 1  # the refunded leg is not a sale count

    assert by_type["card"]["net"] == 75.0

    # Period totals net the refund; the out-of-window row is excluded.
    assert body["total_collected"] == 425.0   # 150 + 200 + 75
    assert body["total_refunds"] == 30.0
    assert body["net"] == 395.0

    # Largest net first → Mada (170) before card (75)? cash 150 > mada 170? No:
    # mada 170 > cash 150 > card 75, so order is mada, cash, card.
    assert [t["tender_type"] for t in body["tenders"]] == ["mada", "cash", "card"]


async def test_payment_breakdown_aggregates_in_sql_not_in_memory(client):
    """OPS-05: the breakdown issues a GROUP BY over payment_tenders."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Volume across few methods → the result set must stay bounded by methods.
    specs = [(1, "cash", 10.0, "captured") for _ in range(40)]
    specs += [(1, "mada", 20.0, "captured") for _ in range(40)]
    await _seed_tenders(client_id, user["id"], specs)

    statements: list[str] = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db_manager.engine.sync_engine, "after_cursor_execute", _capture)
    try:
        resp = await client.get("/api/v1/reports/payment-breakdown?days=30", headers=headers)
    finally:
        event.remove(db_manager.engine.sync_engine, "after_cursor_execute", _capture)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["tenders"]) == 2  # bounded by methods, not by 80 rows

    agg = [
        s for s in statements
        if "payment_tenders" in s.lower() and "group by" in s.lower()
    ]
    assert agg, f"expected a GROUP BY over payment_tenders, got: {statements}"


async def test_payment_breakdown_scoped_to_client(client):
    """SEC-02: an agent is 403; one client never sees another client's tenders."""
    user_a, token_a, client_a = await make_client_account(client)
    user_b, token_b, client_b = await make_client_account(client)

    await _seed_tenders(client_a, user_a["id"], [(1, "cash", 100.0, "captured")])
    await _seed_tenders(client_b, user_b["id"], [(1, "mada", 500.0, "captured")])

    # Client A sees only its own cash tender — not B's 500 Mada.
    resp_a = await client.get("/api/v1/reports/payment-breakdown", headers=auth_headers(token_a))
    assert resp_a.status_code == 200, resp_a.text
    body_a = resp_a.json()
    assert {t["tender_type"] for t in body_a["tenders"]} == {"cash"}
    assert body_a["total_collected"] == 100.0

    # An agent cannot read merchant reports.
    _, agent_token, _ = await make_agent_account(client)
    resp_agent = await client.get(
        "/api/v1/reports/payment-breakdown", headers=auth_headers(agent_token)
    )
    assert resp_agent.status_code == 403, resp_agent.text
