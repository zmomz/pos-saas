"""Issue #230 (Integrations) — accounting/ERP sales-journal export.

The first integration slice: a balanced, double-entry **sales journal** an
accountant (or an ERP import) can post directly. Where the M9 analytics reports
answer "how is the business doing", this answers the bookkeeping question "what
are the debits and credits for this period?".

Every completed sale in the window contributes, by construction, a balanced
posting:

* money received (``total_amount`` + ``tip_amount``) DEBITs a tender asset
  account — cash sales hit *Cash on Hand*, everything else hits *Card & Bank
  Clearing*;
* the VAT collected CREDITs *VAT Payable*;
* any gratuity CREDITs *Gratuities Payable*;
* the remainder (``total_amount`` − ``vat_amount``, i.e. net-of-discount
  revenue) CREDITs *Sales Revenue*.

Credit notes (refunds) reverse the same postings, so the journal nets down and
stays balanced. Held/voided tickets are not selling activity and are excluded.
All figures are tenant-scoped and aggregated server-side (grouped by tender).
"""
from datetime import datetime, timedelta, timezone

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.transactions import Transactions

URL = "/api/v1/reports/accounting-export?lookback=30"


async def _seed(
    client_id,
    user_id,
    *,
    status="completed",
    subtotal=100.0,
    vat=15.0,
    total=115.0,
    tip=0.0,
    method="cash",
    idx=0,
):
    created = datetime.now(timezone.utc) - timedelta(days=2)
    async with db_manager.async_session_maker() as db:
        db.add(
            Transactions(
                user_id=user_id,
                client_id=client_id,
                invoice_number=f"INV-ACC-{client_id}-{status}-{method}-{idx}",
                subtotal=subtotal,
                vat_amount=vat,
                discount_amount=0.0,
                total_amount=total,
                tip_amount=tip,
                payment_method=method,
                status=status,
                created_at=created,
            )
        )
        await db.commit()


def _lines(body):
    return {ln["account_code"]: ln for ln in body["lines"]}


async def test_completed_cash_sale_is_a_balanced_double_entry(client):
    """A cash sale debits Cash and credits Revenue + VAT; the journal balances."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed(client_id, user["id"], subtotal=100.0, vat=15.0, total=115.0)

    resp = await client.get(URL, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["method"] == "sales_journal"
    assert body["lookback_days"] == 30

    lines = _lines(body)
    assert lines["1000"]["debit"] == 115.0  # Cash on Hand
    assert lines["1000"]["credit"] == 0.0
    assert lines["4000"]["credit"] == 100.0  # Sales Revenue = total - vat
    assert lines["2100"]["credit"] == 15.0  # VAT Payable

    assert body["total_debit"] == 115.0
    assert body["total_credit"] == 115.0
    assert body["balanced"] is True


async def test_card_sales_hit_a_distinct_clearing_account(client):
    """Non-cash tenders post to Card & Bank Clearing, not Cash on Hand."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed(client_id, user["id"], method="cash", total=115.0, idx=0)
    await _seed(client_id, user["id"], method="card", total=115.0, idx=1)

    body = (await client.get(URL, headers=headers)).json()
    lines = _lines(body)

    assert lines["1000"]["debit"] == 115.0  # cash
    assert lines["1010"]["debit"] == 115.0  # card & bank clearing
    assert body["balanced"] is True


async def test_tips_post_to_gratuities_payable(client):
    """A gratuity credits Gratuities Payable and lifts the tender debit."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed(client_id, user["id"], subtotal=100.0, vat=15.0, total=115.0, tip=10.0)

    body = (await client.get(URL, headers=headers)).json()
    lines = _lines(body)

    assert lines["1000"]["debit"] == 125.0  # 115 + 10 tip received
    assert lines["2200"]["credit"] == 10.0  # Gratuities Payable
    assert lines["4000"]["credit"] == 100.0
    assert body["balanced"] is True


async def test_credit_notes_reverse_the_posting(client):
    """A refund nets revenue/VAT/cash down; the journal stays balanced."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed(client_id, user["id"], subtotal=100.0, vat=15.0, total=115.0, idx=0)
    # A credit note reversing 20 net + 3 VAT = 23 refunded.
    await _seed(
        client_id,
        user["id"],
        status="credit_note",
        subtotal=20.0,
        vat=3.0,
        total=23.0,
        idx=1,
    )

    body = (await client.get(URL, headers=headers)).json()
    lines = _lines(body)

    assert lines["1000"]["debit"] == 92.0  # 115 in - 23 out
    assert lines["4000"]["credit"] == 80.0  # 100 - 20
    assert lines["2100"]["credit"] == 12.0  # 15 - 3
    assert body["balanced"] is True


async def test_held_and_voided_are_excluded(client):
    """Parked and cancelled tickets are not selling activity — excluded."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed(client_id, user["id"], status="held", idx=0)
    await _seed(client_id, user["id"], status="voided", idx=1)

    body = (await client.get(URL, headers=headers)).json()
    assert body["lines"] == []
    assert body["total_debit"] == 0.0
    assert body["total_credit"] == 0.0
    assert body["balanced"] is True


async def test_export_is_tenant_scoped(client):
    """One tenant's sales never leak into another tenant's journal."""
    _user_a, token_a, _client_a = await make_client_account(client)
    user_b, _token_b, client_b = await make_client_account(client)

    await _seed(client_b, user_b["id"], total=115.0)

    body = (await client.get(URL, headers=auth_headers(token_a))).json()
    assert body["lines"] == []
    assert body["balanced"] is True


async def test_non_client_forbidden(client):
    """Only client accounts can read the accounting export."""
    from conftest import make_agent_account

    _agent, token, _agent_id = await make_agent_account(client)
    resp = await client.get(URL, headers=auth_headers(token))
    assert resp.status_code == 403
