# ISSUE-067 — Per-branch variant stock

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** P2 catalog · **Stories:** 52

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Track stock per variant per branch (rather than a single product/variant total) so transfers, sales, and reports reflect branch-level variant inventory.

## Acceptance criteria
- [ ] Stock is tracked per (variant, branch); sales/transfers adjust the correct branch's level.
- [ ] Migration introduces per-branch variant stock without losing existing totals.
- [ ] Covered by a test (sale at branch A doesn't affect branch B).

## Blocked by
- None - can start immediately
