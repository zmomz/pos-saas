# ISSUE-021 — ProductManagement reads `items` (main catalog table)

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 2 · **Findings:** H6 · **Stories:** 23

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
`getProductsList()` returns `ProductListResponse { items, total }`, but `ProductManagement.loadProducts()` reads `data?.products` → always `[]`, leaving the primary catalog table permanently empty (create/edit/reorder hit other endpoints so the page looks alive). Read `data?.items`.

## Acceptance criteria
- [ ] The product table renders the products returned by `/products/list`.
- [ ] Total/count reflects `total`.
- [ ] A test (or type) guards against reading the wrong key.

## Blocked by
- None - can start immediately
