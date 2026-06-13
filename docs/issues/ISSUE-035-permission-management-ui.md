# ISSUE-035 — Permission-management UI

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 3 · **Findings:** H12 · **Stories:** 37

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
The RBAC engine has no management UI, so a merchant cannot override a role's defaults. Add a staff-permission editor (owner-scoped endpoint + UI) that writes grant/deny rows keyed on staff `user_id`, layered over the role defaults from ISSUE-034. Renders loading/empty/error/permission states, brand tokens, i18n/RTL.

## Acceptance criteria
- [ ] An owner can grant/deny specific permission keys per staff member via the UI.
- [ ] Overrides persist (rows keyed on staff `user_id`) and take effect in `has_permission` over the role default.
- [ ] Endpoint is owner-scoped; cross-tenant edits rejected.
- [ ] Covered by a test.

## Blocked by
- ISSUE-034
