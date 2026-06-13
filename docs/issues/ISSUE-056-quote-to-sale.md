# ISSUE-056 — Quote→sale conversion + quotation status lifecycle

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** P2 pricing · **Stories:** 51

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Quotations are wired but there is no conversion to a sale and no status lifecycle. Add a quote→sale conversion (carrying lines/pricing into the atomic sale path) and a quotation status lifecycle (draft/sent/accepted/expired/converted).

## Acceptance criteria
- [ ] A quotation can be converted into a sale through the canonical sale path (ZATCA-stamped where applicable).
- [ ] Quotation status transitions are enforced and visible.
- [ ] Converting marks the quotation `converted` and links the resulting sale.
- [ ] Covered by a test (create quote → convert → sale exists, status correct).

## Blocked by
- None - can start immediately
