# ISSUE-036 — PO create maps to the real schema

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 3 · **Findings:** C3 · **Stories:** 38

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
`SupplierManagement.handleCreatePO` posts a body missing the required `order_number` (NOT NULL, no default) → 422, and uses `items` where the field is `items_json`, so lines are dropped even if it passed. Map the form to `Purchase_ordersData`: generate `order_number`, send `items_json` with `product_id` per line, drop the phantom fields.

## Acceptance criteria
- [ ] Creating a PO from the UI succeeds (no 422) with a generated `order_number`.
- [ ] Line items persist in `items_json` with `product_id`.
- [ ] Covered by a test mirroring `test_phase6_po_receive.py` creation.

## Blocked by
- None - can start immediately
