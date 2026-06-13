# ISSUE-055 — Agent/master commission statements

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** P2 billing · **Stories:** 50

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Commission logic exists end-to-end but there are no periodic statements. Generate per-period agent/master commission statements summarizing earned commission by client/period, viewable in the relevant dashboard.

## Acceptance criteria
- [ ] A commission statement is generated per agent per period with line items by client.
- [ ] Totals reconcile with the underlying commission records.
- [ ] Viewable in the agent/master dashboard; brand tokens, i18n/RTL.
- [ ] Covered by a test against seeded commission data.

## Blocked by
- None - can start immediately
