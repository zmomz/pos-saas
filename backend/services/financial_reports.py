"""Financial-reporting service — P&L, COGS (BOM roll-up), cash flow (M9, F-068+).

The operational reports (sales summary, top products, payment breakdown, Z-report)
and the first wave of financial reports (profit/margin, VAT summary, inventory
valuation, accounting journal) already live in ``routers/features.py``. This
module adds the two financial statements a POS buyer evaluates the product on but
which were missing — a **Profit & Loss** statement and a **Cash Flow** statement —
plus the **COGS roll-up from the bill of materials** they both share.

Design rules (the same discipline the existing reports follow):

* **Tenant-scoped** — every query is bound by the calling client's ``client_id``;
  there is no cross-tenant path. The caller resolves and passes the id.
* **SQL-aggregated, never load-all (OPS-05)** — money totals are grouped in the
  database; the one place that must read per-line detail (COGS) *streams*
  ``items_json`` row by row against a bounded product-cost map, exactly like the
  existing profit-margin report, rather than materializing the period.
* **Read-only** — these run on the read-replica session (``get_read_db``) so they
  never contend with the sale path; the service never writes.

All amounts are returned as plain rounded floats; the router wraps them in Pydantic
response models and a CSV/PDF rendering, mirroring the sibling reports.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.cash_movements import Cash_movements
from models.expenses import Expenses
from models.products import Products
from models.restaurant import BillOfMaterials
from models.transactions import Transactions

logger = logging.getLogger(__name__)


# A sale's status that excludes it from financial reporting: a held ticket is not a
# fiscal document and a voided sale is reversed in full. Everything else (completed
# sales + credit notes) nets via signed amounts. ``is_distinct_from`` keeps
# NULL-status legacy completed sales in the set.
def _not_excluded():
    return and_(
        Transactions.status.is_distinct_from("held"),
        Transactions.status.is_distinct_from("voided"),
    )


async def effective_cost_map(db: AsyncSession, client_id: int) -> Dict[int, float]:
    """Per-product cost of goods, rolling the bill of materials up onto the parent.

    For a plain catalog product the cost of goods is its own ``cost_price``. For a
    **BOM-backed** product (a made-to-order item: a burger, a coffee) the parent
    frequently carries *no* own cost — its true cost is the sum of its components'
    costs. This rolls that up: ``Σ component.cost_price × qty_per`` becomes the
    parent's effective cost, used wherever a sold line has no sale-time cost
    snapshot. A parent that has *both* its own ``cost_price`` and a BOM keeps its
    own cost (an explicitly costed parent wins over the derived roll-up).

    Two bounded queries (the catalog and the BOM rows for this client) — never the
    transaction stream. Returns ``{product_id: effective_cost}``.
    """
    base_cost: Dict[int, float] = {}
    rows = (
        await db.execute(
            select(Products.id, Products.cost_price).where(Products.client_id == client_id)
        )
    ).all()
    for pid, cost in rows:
        base_cost[int(pid)] = float(cost or 0.0)

    # Roll components up onto their parent: Σ component_base_cost × qty_per.
    bom_rows = (
        await db.execute(
            select(
                BillOfMaterials.parent_product_id,
                BillOfMaterials.component_product_id,
                BillOfMaterials.qty_per,
            ).where(BillOfMaterials.client_id == client_id)
        )
    ).all()
    rolled: Dict[int, float] = {}
    for parent_id, component_id, qty_per in bom_rows:
        comp_cost = base_cost.get(int(component_id), 0.0)
        rolled[int(parent_id)] = rolled.get(int(parent_id), 0.0) + comp_cost * float(qty_per or 0.0)

    effective = dict(base_cost)
    for parent_id, rollup in rolled.items():
        # An explicitly-costed parent keeps its own cost; otherwise the BOM
        # roll-up is its cost of goods.
        if base_cost.get(parent_id, 0.0) <= 0.0:
            effective[parent_id] = round(rollup, 4)
    return effective


async def _sum_revenue(db: AsyncSession, client_id: int, start: datetime, end: datetime) -> Dict[str, float]:
    """Net sales (ex-VAT) for the window, aggregated in one grouped query.

    Revenue on an income statement excludes VAT (a liability, not income). A credit
    note carries negative signed amounts (F-007), so a plain signed SUM nets refunds
    out. Returns gross sales, discounts, net revenue and the VAT collected (carried
    only for context / the journal cross-check).
    """
    row = (
        await db.execute(
            select(
                func.coalesce(func.sum(Transactions.subtotal), 0.0),
                func.coalesce(func.sum(Transactions.discount_amount), 0.0),
                func.coalesce(func.sum(Transactions.vat_amount), 0.0),
            ).where(
                and_(
                    Transactions.client_id == client_id,
                    Transactions.created_at >= start,
                    Transactions.created_at < end,
                    _not_excluded(),
                )
            )
        )
    ).one()
    gross_sales = round(float(row[0] or 0.0), 2)
    discounts = round(float(row[1] or 0.0), 2)
    vat = round(float(row[2] or 0.0), 2)
    net_revenue = round(gross_sales - discounts, 2)
    return {
        "gross_sales": gross_sales,
        "discounts": discounts,
        "vat": vat,
        "net_revenue": net_revenue,
    }


async def _sum_cogs(db: AsyncSession, client_id: int, start: datetime, end: datetime) -> float:
    """Cost of goods sold for the window, netted by credit notes (OPS-05 stream).

    Streams each transaction's ``items_json`` once (bounded memory) and sums each
    line's cost: the sale-time cost snapshot wins (stable historical margin), else
    the BOM-rolled effective cost. A credit note reverses the cost it returned.
    """
    cost_map = await effective_cost_map(db, client_id)
    total = 0.0
    stream = await db.stream(
        select(Transactions.items_json, Transactions.status).where(
            and_(
                Transactions.client_id == client_id,
                Transactions.created_at >= start,
                Transactions.created_at < end,
                _not_excluded(),
            )
        )
    )
    async for items_json, status in stream:
        if not items_json:
            continue
        try:
            items = json.loads(items_json)
        except (json.JSONDecodeError, TypeError):
            continue
        sign = -1.0 if status == "credit_note" else 1.0
        for item in items:
            pid = item.get("product_id")
            qty = float(item.get("quantity", 0) or 0)
            snap = item.get("cost_price")
            if snap is not None:
                cost = float(snap)
            else:
                cost = cost_map.get(int(pid), 0.0) if pid is not None else 0.0
            total += sign * cost * qty
    return round(total, 2)


async def _expenses_by_category(
    db: AsyncSession, client_id: int, start: datetime, end: datetime
) -> List[Dict[str, Any]]:
    """Operating expenses for the window, grouped by category in SQL.

    Windowed on ``created_at`` (the row's recorded timestamp) for parity with every
    other report — ``expense_date`` is a free-text field and unreliable for a SQL
    range. Result set is bounded by the number of expense categories.
    """
    rows = (
        await db.execute(
            select(
                Expenses.category,
                func.coalesce(func.sum(Expenses.amount), 0.0),
            )
            .where(
                and_(
                    Expenses.client_id == client_id,
                    Expenses.created_at >= start,
                    Expenses.created_at < end,
                )
            )
            .group_by(Expenses.category)
        )
    ).all()
    out = [
        {"category": (cat or "Uncategorized"), "amount": round(float(amt or 0.0), 2)}
        for cat, amt in rows
    ]
    out.sort(key=lambda r: (-r["amount"], r["category"]))
    return out


def _margin_pct(base: float, value: float) -> float:
    """``value`` as a % of ``base`` (0 when there is no base)."""
    return round((value / base) * 100, 2) if base else 0.0


async def compute_pnl(
    db: AsyncSession, client_id: int, start: datetime, end: datetime
) -> Dict[str, Any]:
    """Build a Profit & Loss statement for ``[start, end)``, tenant-scoped.

    Revenue (net of discounts, ex-VAT) − COGS (BOM-rolled) = gross profit; less
    operating expenses (by category) = net profit. Every figure is SQL-aggregated
    or streamed, never load-all.
    """
    rev = await _sum_revenue(db, client_id, start, end)
    cogs = await _sum_cogs(db, client_id, start, end)
    expenses = await _expenses_by_category(db, client_id, start, end)
    total_expenses = round(sum(e["amount"] for e in expenses), 2)

    net_revenue = rev["net_revenue"]
    gross_profit = round(net_revenue - cogs, 2)
    net_profit = round(gross_profit - total_expenses, 2)
    return {
        "gross_sales": rev["gross_sales"],
        "discounts": rev["discounts"],
        "net_revenue": net_revenue,
        "vat": rev["vat"],
        "cogs": cogs,
        "gross_profit": gross_profit,
        "gross_margin_pct": _margin_pct(net_revenue, gross_profit),
        "expenses": expenses,
        "total_expenses": total_expenses,
        "net_profit": net_profit,
        "net_margin_pct": _margin_pct(net_revenue, net_profit),
    }


async def _receipts_by_tender(
    db: AsyncSession, client_id: int, start: datetime, end: datetime
) -> List[Dict[str, Any]]:
    """Cash actually received per payment method, net of refunds (one GROUP BY).

    Reads the captured ``payment_tenders`` rows — what truly settled per method —
    keyed by (tender_type, status), exactly like the payment-breakdown report.
    """
    from models.payment_tenders import PaymentTenders

    rows = (
        await db.execute(
            select(
                PaymentTenders.tender_type,
                PaymentTenders.status,
                func.coalesce(func.sum(PaymentTenders.amount), 0.0),
            )
            .where(
                and_(
                    PaymentTenders.client_id == client_id,
                    PaymentTenders.created_at >= start,
                    PaymentTenders.created_at < end,
                    PaymentTenders.status != "declined",
                )
            )
            .group_by(PaymentTenders.tender_type, PaymentTenders.status)
        )
    ).all()
    buckets: Dict[str, Dict[str, float]] = {}
    for tender_type, status, amount in rows:
        key = tender_type or "unknown"
        b = buckets.setdefault(key, {"collected": 0.0, "refunds": 0.0})
        amount = float(amount or 0.0)
        if status == "refunded":
            b["refunds"] += amount
        else:
            b["collected"] += amount
    out = [
        {
            "tender_type": k,
            "collected": round(v["collected"], 2),
            "refunds": round(v["refunds"], 2),
            "net": round(v["collected"] - v["refunds"], 2),
        }
        for k, v in buckets.items()
    ]
    out.sort(key=lambda r: (-r["net"], r["tender_type"]))
    return out


async def _drawer_movements(
    db: AsyncSession, client_id: int, start: datetime, end: datetime
) -> Dict[str, float]:
    """Cash-drawer movement totals for the window, grouped by type in SQL.

    pay_in / pay_out / cash_drop magnitudes (POS-09). These are drawer float
    management — largely internal transfers — so they are reported on their own,
    not folded into operating cash flow (only ``pay_out`` is true cash leaving the
    business for petty-cash/supplier, and we surface it for the operator to judge).
    """
    rows = (
        await db.execute(
            select(
                Cash_movements.movement_type,
                func.coalesce(func.sum(Cash_movements.amount), 0.0),
            )
            .where(
                and_(
                    Cash_movements.client_id == client_id,
                    Cash_movements.created_at >= start,
                    Cash_movements.created_at < end,
                )
            )
            .group_by(Cash_movements.movement_type)
        )
    ).all()
    totals = {r[0]: round(float(r[1] or 0.0), 2) for r in rows}
    pay_in = totals.get("pay_in", 0.0)
    pay_out = totals.get("pay_out", 0.0)
    cash_drop = totals.get("cash_drop", 0.0)
    return {
        "pay_in": pay_in,
        "pay_out": pay_out,
        "cash_drop": cash_drop,
        # Net change in the physical drawer from non-sale movements.
        "net_drawer": round(pay_in - pay_out - cash_drop, 2),
    }


async def compute_cash_flow(
    db: AsyncSession, client_id: int, start: datetime, end: datetime
) -> Dict[str, Any]:
    """Build a cash-basis Cash Flow statement for ``[start, end)``, tenant-scoped.

    Operating cash flow = customer receipts (all tenders, net of refunds) − cash
    operating expenses. The receipts-by-tender split and the drawer-movement
    totals are surfaced alongside for traceability. All SQL-aggregated.
    """
    by_tender = await _receipts_by_tender(db, client_id, start, end)
    receipts_net = round(sum(t["net"] for t in by_tender), 2)
    receipts_collected = round(sum(t["collected"] for t in by_tender), 2)
    receipts_refunds = round(sum(t["refunds"] for t in by_tender), 2)

    expenses = await _expenses_by_category(db, client_id, start, end)
    total_expenses = round(sum(e["amount"] for e in expenses), 2)

    drawer = await _drawer_movements(db, client_id, start, end)

    inflows = [{"label": "Sales receipts (net of refunds)", "amount": receipts_net}]
    outflows = [{"label": "Operating expenses", "amount": total_expenses}]
    net_cash_flow = round(receipts_net - total_expenses, 2)
    return {
        "receipts_collected": receipts_collected,
        "receipts_refunds": receipts_refunds,
        "receipts_net": receipts_net,
        "by_tender": by_tender,
        "expenses": expenses,
        "total_expenses": total_expenses,
        "inflows": inflows,
        "outflows": outflows,
        "net_cash_flow": net_cash_flow,
        "drawer_movements": drawer,
    }
