# ISSUE-104 — Fix deplete-stock double-deduct

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** U4.1 (solid-unit minor) · **Stories:** Further Notes

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
In the restaurant settle path, deplete-stock double-deducts (a known data-integrity trap in an otherwise solid unit). Fix so each component/product is depleted exactly once per sale. Coordinate with the combo expansion in ISSUE-032 to avoid re-introducing a double-count.

## Acceptance criteria
- [ ] Settling a ticket depletes each product/component exactly once.
- [ ] No regression with combo expansion (ISSUE-032) or BOM depletion.
- [ ] Covered by a test asserting single deduction per line/component.

## Blocked by
- ISSUE-032
