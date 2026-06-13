# ISSUE-022 — ExpenseTracking reads `items` / `total_amount`

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 2 · **Findings:** H8 · **Stories:** 24

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
ExpenseTracking reads `txData.transactions` and reduces on `tx.total`; the endpoint returns `items` with `total_amount`, so the Revenue and Net Profit/Loss cards are permanently wrong (0). Read `txData.items` and sum `tx.total_amount`.

## Acceptance criteria
- [ ] Revenue and Net Profit/Loss cards compute from `items`/`total_amount` and show correct figures.
- [ ] Verified against seeded demo data.
- [ ] Guarded by a type/test.

## Blocked by
- None - can start immediately
