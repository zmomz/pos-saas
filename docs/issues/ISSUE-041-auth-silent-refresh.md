# ISSUE-041 — Auth: silent token refresh in the 401 interceptor

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 3 · **Findings:** H10 · **Stories:** 43

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
The backend issues refresh tokens and exposes `POST /auth/refresh`; the frontend stores and implements `refreshAccessToken()` but nothing calls it — the 401 interceptor clears the token and bounces to `/login`, so sessions hard-expire at the 24h access boundary and the 7-day refresh token does nothing. Wire `refreshAccessToken()` into the 401 interceptor: attempt one refresh + replay the original request before clearing/redirecting. (This supersedes the "dead `refreshAccessToken`" cleanup — wire it, don't delete it.)

## Acceptance criteria
- [ ] On a 401, the interceptor attempts exactly one refresh and replays the original request.
- [ ] A user with a valid refresh token stays signed in past the 24h access boundary.
- [ ] On refresh failure, the user is cleanly logged out/redirected (no loop).
- [ ] Covered by a test (expired access + valid refresh → request succeeds after one refresh).

## Blocked by
- None - can start immediately
