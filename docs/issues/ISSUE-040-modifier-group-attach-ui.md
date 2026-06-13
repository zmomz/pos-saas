# ISSUE-040 — Product↔modifier-group attach UI

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 3 · **Findings:** U4.2 dead binding · **Stories:** 42

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
`api.ts` `attachModifierGroup`/`detachModifierGroup` are exported with no caller. Add a UI (product detail / MenuBuilder) to attach and detach modifier groups to products so the existing clients are reachable and modifiers flow into ordering.

## Acceptance criteria
- [ ] A merchant can attach/detach modifier groups to a product in-app.
- [ ] Attachments persist and surface in the ordering flow.
- [ ] Covered by a test.

## Blocked by
- None - can start immediately
