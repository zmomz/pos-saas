# ISSUE-034 — Role→permission default map drives `has_permission`

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 3 · **Findings:** H12 · **Stories:** 36

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
`staff_members.role` is never translated to permission-key grant/deny rows; `require_permission` (pos.refund/void) fires only for hand-seeded data. Drive `has_permission` off a role→`permission_key` default map so a real merchant's staff get enforced permissions by role. Reconcile or drop the ignored NOT-NULL `Permissions.role` column.

## Acceptance criteria
- [ ] A default role→permission_key map exists; `has_permission` resolves a staff member's role to permissions.
- [ ] A cashier role is denied `pos.refund`/`pos.void`/discount where the map says so; a manager is allowed.
- [ ] `Permissions.role` is reconciled (used) or dropped.
- [ ] Covered by a test asserting allow/deny by role.

## Blocked by
- ISSUE-033
