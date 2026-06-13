# ISSUE-081 — Multi-factor authentication (MFA)

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** P2 auth · **Stories:** 56

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Add optional MFA (TOTP) — enroll, verify on login, recovery codes.

## Acceptance criteria
- [ ] A user can enroll TOTP and is challenged for it on login.
- [ ] Recovery codes work and are single-use.
- [ ] Covered by a test (enroll → login requires code → recovery works).

## Blocked by
- None - can start immediately
