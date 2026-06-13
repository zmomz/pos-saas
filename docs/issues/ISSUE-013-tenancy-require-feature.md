# ISSUE-013 — Tenancy: `require_feature` resolves the owning merchant's entitlements

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 1 · **Findings:** U0.2 feature-gate · **Stories:** 14, 59

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
`require_feature` scopes on the calling user rather than the owning merchant, so staff/cashiers get 403 on gated routes their merchant has paid for. Resolve entitlements against `owner_user_id` via the tenant scope so a sub-user inherits their merchant's feature flags.

## Acceptance criteria
- [ ] `require_feature` checks the owning merchant's entitlements via the tenant scope.
- [ ] A staff sub-user reaches a gated route their owner is entitled to.
- [ ] A sub-user of a non-entitled merchant is still 403'd.
- [ ] Case added to `tests/test_phase1_tenant_scope.py`.

## Blocked by
- None - can start immediately
