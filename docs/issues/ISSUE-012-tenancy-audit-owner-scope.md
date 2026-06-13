# ISSUE-012 — Tenancy: owner-scope audit/api-usage reads + tag rows with owner

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 1 · **Findings:** H4 · **Stories:** 13, 59

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
`audit_logs`/`api_usage` scope reads on raw `current_user.id`, and the middleware records actions under the staff member's `sub`, so a merchant owner's audit query shows only their *own* actions and all staff activity is invisible — the inverse of the feature. Inject `get_tenant_scope`, scope reads to `owner_user_id`, and tag each audit/metering row with the owning merchant.

## Acceptance criteria
- [ ] Audit/api-usage GET endpoints scope on `owner_user_id`.
- [ ] The audit middleware tags rows with the owning merchant (resolved via tenant scope), not only the actor `sub`.
- [ ] An owner's audit query returns actions performed by their staff.
- [ ] Cross-tenant reads are rejected; case added to `tests/test_phase1_tenant_scope.py`.

## Blocked by
- ISSUE-006, ISSUE-007 (read-only endpoints must be the final form to scope)
