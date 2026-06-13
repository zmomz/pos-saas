# ISSUE-039 — BOM recipe editor (client + UI)

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 3 · **Findings:** H22 · **Stories:** 41

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Recipe endpoints + service + sale-core deduction are built and tested, but there is no BOM `api.ts` client and no UI, so a merchant can never define a recipe in-app (depletion only fires for raw-API-seeded recipes). Add BOM client functions + a recipe editor (product detail or a MenuBuilder tab).

## Acceptance criteria
- [ ] BOM `api.ts` client functions exist for the recipe endpoints.
- [ ] A merchant can define/edit a recipe (component product + qty) in-app.
- [ ] Selling a product with a UI-defined recipe depletes its components (existing sale-core path).
- [ ] Covered by a test (define recipe in app surface → sale depletes components).

## Blocked by
- None - can start immediately
