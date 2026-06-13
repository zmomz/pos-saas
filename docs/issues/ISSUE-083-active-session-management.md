# ISSUE-083 — Active-session management

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** P2 auth · **Stories:** 56

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Let a user view their active sessions (refresh-token jtis) and revoke them individually or all-but-current.

## Acceptance criteria
- [ ] A user can list active sessions with basic metadata.
- [ ] Revoking a session invalidates its refresh token (subsequent `/auth/refresh` fails).
- [ ] Covered by a test (login twice → revoke one → that one's refresh fails).

## Blocked by
- ISSUE-042
