# ISSUE-042 — Auth: single correct logout that revokes the refresh token

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 3 · **Findings:** H11 · **Stories:** 44

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Two divergent logouts exist: `AuthContext.logout()` sends `refresh_token` and clears both keys, while the three dashboards call `client.auth.logout()` which POSTs no body (server never revokes the jti — session resurrectable via `/auth/refresh`) and leaves `pos_refresh_token` in localStorage. Make the dashboards call `useAuth().logout()` (or delegate to it) and remove the duplicate.

## Acceptance criteria
- [ ] All logout paths revoke the refresh-token jti server-side and clear both localStorage keys.
- [ ] After logout, a subsequent `/auth/refresh` with the old token fails.
- [ ] The duplicate `client.auth.logout()` is removed.
- [ ] Covered by a test (logout → refresh rejected).

## Blocked by
- None - can start immediately
