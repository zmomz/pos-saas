# ISSUE-059 — Unique discount codes

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** P2 pricing · **Stories:** 51

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Add single-use / unique discount codes (generated in batches, redeemable once, with validity windows) distinct from the reusable discount definitions.

## Acceptance criteria
- [ ] Unique codes can be generated and redeemed exactly once within their validity window.
- [ ] A redeemed/expired code is rejected at apply time.
- [ ] Covered by a test (generate → redeem → second redeem rejected).

## Blocked by
- None - can start immediately
