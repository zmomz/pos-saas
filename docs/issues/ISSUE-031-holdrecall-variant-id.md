# ISSUE-031 — Hold/recall preserves `variant_id` + open price

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 2 · **Findings:** H28 · **Stories:** 33

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
`handleHold` drops `variant_id` and open-price `unitPrice`; `handleRecall` rebuilds lines keyed on `cartKeyFor(product_id)` only. A held variant SKU returns as a plain product → `execute_sale` deducts the **parent** product's stock, variant siblings collapse to one key, open-price reverts to catalog. Backend round-trips `items_json` verbatim, so this is a frontend serialization fix: carry `variant_id` + `unitPrice` through hold→`items_json`→recall and key with `cartKeyFor(product_id, variant_id)`.

## Acceptance criteria
- [ ] Holding then recalling a variant SKU restores its `variant_id`, open price, and distinct cart key.
- [ ] A recalled variant sale deducts the variant's stock, not the parent's.
- [ ] Two different variants of one product remain separate lines after recall.
- [ ] Covered by a test.

## Blocked by
- None - can start immediately
