# ISSUE-038 — Product↔category linkage

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 3 · **Findings:** H7 · **Stories:** 40

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Products store free-text `category` (no FK), the product form uses a hardcoded `CATEGORIES` array, and `features.py` never references the full categories model/service/router/UI island — so a merchant's category tree can't be assigned to products. Add a `products.category_id` FK and source the product form Select from `getCategories()`, removing the hardcoded array. (If the team decides categories stay unused, the alternative is dropping the categories CRUD — but linkage is preferred for parity.)

## Acceptance criteria
- [ ] `products.category_id` FK added (with migration); product create/edit assigns a real category.
- [ ] The product form category Select is sourced from `getCategories()`.
- [ ] Product lists/filters can use the linked category.
- [ ] Covered by a test (assign category → persists → filter works).

## Blocked by
- None - can start immediately
