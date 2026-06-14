"""The promotion engine — auto-applied line/category/BOGO discounts (ISSUE-058).

The order-level coded discount (:mod:`services.discounts`) prices a single flat or
percentage amount against the whole order and must be entered by code. Merchants
also need promotions that target *part* of the cart and *fire on their own* when
the cart meets a condition:

* **line** — a % or fixed discount on a specific product;
* **category** — a % or fixed discount on every line in a category;
* **bogo** — buy-N-get-M (free or % off) on a specific product.

:func:`compute_promotions` is the pure heart of the feature: given the cart lines
and a set of active rules it returns the total promotion discount and a per-rule
breakdown, with no DB or I/O. The caller (the POS sale path / the preview
endpoint) folds ``total_discount`` into the order ``discount_amount`` so it reduces
the taxable base *before* VAT — composing with VAT exactly like the order discount.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class CartLine:
    """One cart line the engine prices against (a POS ``CartItem`` projection)."""

    price: float
    quantity: float
    product_id: Optional[int] = None
    category: Optional[str] = None


@dataclass
class PromoRule:
    """An auto-applied promotion rule (mirrors the ``Promotions`` ORM columns).

    ``kind`` selects the matcher/pricer: ``line`` and ``category`` discount the
    matching lines by ``value`` as ``disc_type`` (``percentage``/``fixed``); ``bogo``
    discounts ``bogo_get_qty`` units by ``bogo_get_percent`` for every
    ``bogo_buy_qty + bogo_get_qty`` of the target product bought. A rule only fires
    when active and the cart subtotal meets ``min_subtotal`` (None ⇒ no floor).
    """

    name: str
    kind: str
    id: Optional[int] = None
    disc_type: str = "percentage"
    value: float = 0.0
    product_id: Optional[int] = None
    category: Optional[str] = None
    min_subtotal: Optional[float] = None
    bogo_buy_qty: int = 1
    bogo_get_qty: int = 1
    bogo_get_percent: float = 100.0
    is_active: bool = True


@dataclass
class AppliedPromotion:
    """One promotion that fired, and the discount it contributed (>= 0)."""

    promotion_id: Optional[int]
    name: str
    kind: str
    amount: float


@dataclass
class PromotionResult:
    """The outcome of pricing a cart against a set of rules."""

    total_discount: float
    applied: List[AppliedPromotion] = field(default_factory=list)


def _discount_on_base(disc_type: str, value: float, base: float) -> float:
    """A %/fixed discount on ``base``, clamped to ``[0, base]``."""
    if (disc_type or "").lower() in ("percentage", "percent", "%"):
        amount = base * (float(value or 0) / 100.0)
    else:  # fixed / flat
        amount = float(value or 0)
    return round(max(0.0, min(amount, base)), 2)


def _amount_for_rule(rule: Any, lines: List[CartLine]) -> float:
    """The discount one rule contributes to the cart (0 when nothing matches)."""
    kind = (getattr(rule, "kind", "") or "").lower()
    if kind == "line":
        base = sum(l.price * l.quantity for l in lines if l.product_id == rule.product_id)
        return _discount_on_base(rule.disc_type, rule.value, base)
    if kind == "category":
        target = (rule.category or "").strip().lower()
        base = sum(
            l.price * l.quantity
            for l in lines
            if (l.category or "").strip().lower() == target
        )
        return _discount_on_base(rule.disc_type, rule.value, base)
    if kind == "bogo":
        return _bogo_amount(rule, lines)
    return 0.0


def _bogo_amount(rule: Any, lines: List[CartLine]) -> float:
    """Buy-N-get-M discount on the target product (cheapest-unit semantics).

    For every ``buy + get`` units of the target product in the cart, ``get`` units
    are discounted by ``bogo_get_percent`` (100 ⇒ free). The discount is priced at
    the target line's unit price.
    """
    buy = max(0, int(rule.bogo_buy_qty or 0))
    get = max(0, int(rule.bogo_get_qty or 0))
    group = buy + get
    if group <= 0 or get <= 0:
        return 0.0
    target = [l for l in lines if l.product_id == rule.product_id]
    qty = sum(l.quantity for l in target)
    unit_price = target[0].price if target else 0.0
    free_units = int(qty // group) * get
    return round(free_units * unit_price * (float(rule.bogo_get_percent or 0) / 100.0), 2)


def compute_promotions(lines: List[CartLine], rules: List[Any]) -> PromotionResult:
    """Price ``lines`` against every active, condition-met ``rule`` (pure).

    A rule fires only when it is active and the cart subtotal meets its
    ``min_subtotal`` floor; each firing rule contributes its own discount and the
    sum is clamped to the subtotal so promotions can never push the order negative.
    The returned ``applied`` list is what surfaces to the cashier.
    """
    subtotal = round(sum(l.price * l.quantity for l in lines), 2)
    applied: List[AppliedPromotion] = []
    for rule in rules:
        if getattr(rule, "is_active", True) is False:
            continue
        floor = getattr(rule, "min_subtotal", None)
        if floor is not None and subtotal < float(floor):
            continue
        amount = _amount_for_rule(rule, lines)
        if amount > 0:
            applied.append(
                AppliedPromotion(
                    promotion_id=getattr(rule, "id", None),
                    name=getattr(rule, "name", ""),
                    kind=(getattr(rule, "kind", "") or "").lower(),
                    amount=amount,
                )
            )
    total = round(min(sum(a.amount for a in applied), subtotal), 2)
    return PromotionResult(total_discount=total, applied=applied)


# ---------------------------------------------------------------------------
# DB-aware glue: load the owner's rules and project cart items into CartLines
# ---------------------------------------------------------------------------
async def load_active_promotions(db: AsyncSession, user_id: str) -> List[Any]:
    """All active promotion rules in the owner's scope (newest first)."""
    from models.promotions import Promotions

    rows = (
        await db.execute(
            select(Promotions)
            .where(
                Promotions.user_id == str(user_id),
                Promotions.is_active.isnot(False),
            )
            .order_by(Promotions.id.desc())
        )
    ).scalars().all()
    return list(rows)


async def build_cart_lines(
    db: AsyncSession, client_id: int, items: List[Any]
) -> List[CartLine]:
    """Project POS cart items into :class:`CartLine`, resolving each product's category.

    Category promotions match on the catalog ``category`` string, which the POS cart
    line does not carry, so we look it up once for all referenced products. Ad-hoc
    lines (no catalog product) keep a null category and only ever match line/BOGO
    promos by ``product_id``.
    """
    from models.products import Products

    pids = {int(p) for it in items if (p := getattr(it, "product_id", None)) is not None}
    category_of: dict[int, Optional[str]] = {}
    if pids:
        rows = (
            await db.execute(
                select(Products.id, Products.category).where(
                    Products.id.in_(pids),
                    Products.client_id == client_id,
                )
            )
        ).all()
        category_of = {pid: cat for pid, cat in rows}
    return [
        CartLine(
            price=float(getattr(it, "price", 0) or 0),
            quantity=float(getattr(it, "quantity", 0) or 0),
            product_id=getattr(it, "product_id", None),
            category=category_of.get(int(getattr(it, "product_id", 0) or 0)),
        )
        for it in items
    ]


async def price_cart_promotions(
    db: AsyncSession, user_id: str, client_id: int, items: List[Any]
) -> PromotionResult:
    """Load the owner's active rules, project the cart, and price the promotions."""
    rules = await load_active_promotions(db, user_id)
    if not rules:
        return PromotionResult(total_discount=0.0, applied=[])
    lines = await build_cart_lines(db, client_id, items)
    return compute_promotions(lines, rules)
