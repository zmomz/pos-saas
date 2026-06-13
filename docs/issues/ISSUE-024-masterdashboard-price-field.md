# ISSUE-024 — MasterDashboard reads the real per-client price field

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 2 · **Findings:** U1.1 contract drift · **Stories:** 26

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
MasterDashboard reads `retail_price_per_client` (a field the API doesn't return under that name), rendering 0. Read the real price field from the master metrics payload.

## Acceptance criteria
- [ ] The per-client price metric renders the actual figure (non-zero against seeded data).
- [ ] Guarded by a type/test.

## Blocked by
- None - can start immediately
