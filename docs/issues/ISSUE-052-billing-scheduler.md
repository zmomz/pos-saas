# ISSUE-052 — Always-on billing scheduler (dunning/retry auto-sweep)

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** P2 billing · **Stories:** 50

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Billing/dunning/commission logic exists but there is no always-on scheduler, so dunning/retry only runs on manual trigger. Add a scheduled sweep that runs the billing/dunning/retry cycle automatically.

## Acceptance criteria
- [ ] A scheduled job runs the billing/dunning/retry sweep without manual triggering.
- [ ] Overdue subscriptions advance through dunning states automatically.
- [ ] The sweep is idempotent (re-running does not double-charge/double-advance).
- [ ] Covered by a test invoking the sweep against seeded overdue data.

## Blocked by
- None - can start immediately
