# ISSUE-064 — Catalog CSV import/export

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** P2 catalog · **Stories:** 52

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Add CSV import and export for the product catalog so merchants can bulk-create/update products and export their catalog, with validation and an error report for bad rows.

## Acceptance criteria
- [ ] Export produces a CSV of the merchant's catalog.
- [ ] Import creates/updates products from a CSV; invalid rows are reported, not silently dropped.
- [ ] Covered by a test (round-trip export → import).

## Blocked by
- None - can start immediately
