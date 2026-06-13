# ISSUE-065 — Product images

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** P2 catalog · **Stories:** 52

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Add product image upload/display (used in catalog and POS tile grid). Depends on working object storage (ISSUE-030 outcome) for persistence.

## Acceptance criteria
- [ ] A merchant can upload a product image; it displays in catalog and POS.
- [ ] Images persist via the storage backend; reasonable size/type validation.
- [ ] Covered by a test (upload → reference persisted → renders).

## Blocked by
- ISSUE-030
