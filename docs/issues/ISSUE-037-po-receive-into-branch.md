# ISSUE-037 — PO receive into branch + partial receipts

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 3 · **Findings:** H19 · **Stories:** 39

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Receive keys off `product_id` per `items_json` line, but the create form only collects `product_name`, so UI POs fall into the "no receivable lines → close with 0 stock" branch; `receivePurchaseOrder` is also called with no options, so branch/partial receipts (the INV-07 headline) are unreachable. Capture `product_id` on lines (delivered by ISSUE-036) and add a receive dialog with branch + per-line quantities.

## Acceptance criteria
- [ ] Receiving a UI-created PO lands stock for each line (`product_id` present).
- [ ] A receive dialog supports selecting a branch and per-line received quantities (partial receipts).
- [ ] Partial receipt leaves the PO in the correct partially-received state.
- [ ] Covered by a test (create → partial receive → stock + state correct).

## Blocked by
- ISSUE-036, ISSUE-010
