# ISSUE-082 — Password reset / forgot-password

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** P2 auth · **Stories:** 56

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Add a forgot-password flow: request reset → time-limited token (delivered via notification channel) → set new password.

## Acceptance criteria
- [ ] A user can request a reset and complete it with a time-limited token.
- [ ] Used/expired tokens are rejected; old sessions handled per policy.
- [ ] Covered by a test (request → reset → login with new password).

## Blocked by
- None - can start immediately
