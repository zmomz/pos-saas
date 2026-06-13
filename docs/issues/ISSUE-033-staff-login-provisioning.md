# ISSUE-033 — Staff login provisioning

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 3 · **Findings:** H21 · **Stories:** 35

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
StaffManagement create/update writes a `Staff_members` row with no auth User and no password/invite, so a "cashier" cannot log in (tenancy resolution matches `Staff_members.email` to an *existing* `User.email` that nothing creates). On staff create/update, create or link an auth `User` (temp password or invite token) scoped to the merchant. Until shipped, the screen is honestly labeled "staff directory."

## Acceptance criteria
- [ ] Creating a staff member provisions/links a `User` scoped to the merchant.
- [ ] The new staff member can authenticate (temp password or invite-accept flow).
- [ ] Tenancy resolution finds the staff user under the owning merchant.
- [ ] Covered by a test (create staff → login succeeds → scoped to owner).

## Blocked by
- None - can start immediately
