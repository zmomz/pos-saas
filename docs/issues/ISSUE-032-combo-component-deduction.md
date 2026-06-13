# ISSUE-032 — Combo lines deduct component stock at settle

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 2 · **Findings:** H23 · **Stories:** 34

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Combo lines are created with `product_id=None`, so settle's `_cart_lines` carries None and `sale_core` skips inventory + BOM for them — selling a combo charges the bundle but decrements **no** stock and routes nothing to the kitchen (silent oversell). At settle, expand combo lines into their component products (id + qty) so deduction + KDS routing fire; or explicitly document combos as non-stock bundles.

## Acceptance criteria
- [ ] Selling a combo decrements each component product's stock by its quantity within the same atomic sale.
- [ ] Combo components route to the kitchen (KDS) where applicable.
- [ ] Covered by extending the restaurant settle tests.

## Blocked by
- None - can start immediately
