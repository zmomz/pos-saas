# ISSUE-062 — Branch `is_main` UI

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** P2 inventory · **Stories:** 52

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
The branch model carries `is_main` but there is no UI to set it. Add a control to designate the main branch (exactly one), used by defaults across the app.

## Acceptance criteria
- [ ] A merchant can set exactly one branch as main via the UI.
- [ ] Setting a new main unsets the previous; persisted.
- [ ] Covered by a test.

## Blocked by
- None - can start immediately
