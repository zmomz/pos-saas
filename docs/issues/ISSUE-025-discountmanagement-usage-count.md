# ISSUE-025 — DiscountManagement reads `usage_count`

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 2 · **Findings:** U3.5 inert binding · **Stories:** 28

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
DiscountManagement reads `used_count` while the API returns `usage_count`, so "Total Uses" is always 0. Read `usage_count`.

## Acceptance criteria
- [ ] "Total Uses" renders the real usage count.
- [ ] Guarded by a type/test.

## Blocked by
- None - can start immediately
