# ISSUE-068 — Soft-delete products

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** P2 catalog · **Stories:** 52

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Deleting a product should soft-delete (archive) it so historical sales/reports remain intact and the SKU can be restored, rather than hard-deleting referenced rows.

## Acceptance criteria
- [ ] Deleting a product archives it; it disappears from active catalog/POS but historical references resolve.
- [ ] Archived products can be restored.
- [ ] Covered by a test (delete → hidden from catalog, still on past sale → restore).

## Blocked by
- None - can start immediately
