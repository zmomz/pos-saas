# ISSUE-010 — Tenancy: scope PO-receive on the owning merchant

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 1 · **Findings:** H18 · **Stories:** 11, 59

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
`receive_purchase_order` filters `Purchase_orders.user_id == str(current_user.id)`, unlike every other CRUD/transfer/adjustment route, so a staff cashier who can list POs gets a 404 receiving them. Inject `TenantScope`/`get_owner_id` and filter on `owner_user_id`.

## Acceptance criteria
- [ ] PO-receive scopes on `owner_user_id` via `Depends(get_owner_id)`/`get_tenant_scope`.
- [ ] A staff/cashier sub-user of a merchant can receive a PO their owner created (no 404).
- [ ] Cross-tenant receive is still rejected.
- [ ] Case added to `tests/test_phase1_tenant_scope.py`.

## Blocked by
- None - can start immediately
