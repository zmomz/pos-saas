# ISSUE-044 — Loyalty points ledger + expiry

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 3 · **Findings:** P1 loyalty · **Stories:** 46

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Build on the loyalty admin endpoints (ISSUE-028) with a points-movement ledger (every earn/redeem/adjust recorded as a dated entry) and an expiry policy so balances are auditable and points age out.

## Acceptance criteria
- [ ] Every earn/redeem/adjust writes a dated ledger entry; balance equals the ledger sum minus expired.
- [ ] Points expire per a configurable policy; expired points reduce the usable balance.
- [ ] The transactions/history view reflects the ledger.
- [ ] Covered by a test (earn → expiry window → balance reduced).

## Blocked by
- ISSUE-028
