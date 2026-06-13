# ISSUE-061 — Two-phase stock transfer

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** P2 inventory · **Stories:** 52

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Add a two-phase transfer (dispatch → receive) so stock leaves the source on dispatch and lands at the destination only on receive, with an in-transit state and discrepancy handling.

## Acceptance criteria
- [ ] Dispatch decrements source and marks stock in-transit; receive increments destination.
- [ ] Discrepancies between dispatched and received quantities are recorded.
- [ ] Covered by a test for the full dispatch→receive cycle.

## Blocked by
- ISSUE-060
