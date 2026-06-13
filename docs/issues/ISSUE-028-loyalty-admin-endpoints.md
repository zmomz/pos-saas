# ISSUE-028 — Loyalty admin: implement the 4 missing endpoints + wire UI

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 2 · **Findings:** C4 · **Stories:** 30

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
LoyaltyProgram calls `/loyalty/config` (GET+POST), `/loyalty/balances`, `/loyalty/transactions`, `/loyalty/adjust` — none exist (backend only has `/loyalty/earn|redeem|balance`). Implement the four (config↔`loyalty_programs`, balances↔`loyalty_points`, transactions ledger, adjust) or rewire onto real surfaces, reconciling the singular `/loyalty/balance` vs the plural the UI calls. Config Save persists, balances/history populate, Adjust mutates.

## Acceptance criteria
- [ ] All four endpoints exist and round-trip; config Save persists and reloads.
- [ ] Balances and transactions render real data; Adjust changes a balance and writes a ledger entry.
- [ ] The `/loyalty` page no longer relies on swallowed 404s.
- [ ] Endpoints covered by tests.

## Blocked by
- ISSUE-020
