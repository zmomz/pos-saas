# ISSUE-011 — Tenancy: scope payments-gateway on the owning merchant

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 1 · **Findings:** H17 · **Stories:** 12, 59

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
`payments_gateway.py` scopes every op by `str(current_user.id)` (`_client_for_user`, register/list/charge), unlike the owner-scoped sale path, so a cashier hits 403 on `/charge` and an empty `/terminals`. Replace per-handler scoping with `Depends(get_owner_id)`.

## Acceptance criteria
- [ ] register/list/charge all resolve the client via `get_owner_id`.
- [ ] A cashier sub-user can list terminals and charge against the owner's terminals.
- [ ] Cross-tenant access is rejected.
- [ ] Case added to `tests/test_phase1_tenant_scope.py`.

## Blocked by
- None - can start immediately
