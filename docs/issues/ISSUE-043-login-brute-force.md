# ISSUE-043 — Login brute-force protection

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 3 · **Findings:** U0.1 · **Stories:** 45

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
The login endpoint has no brute-force protection. Add throttling/lockout (e.g. rate-limit by identifier + IP, escalating backoff or temporary lockout after N failures) so credential-stuffing is mitigated.

## Acceptance criteria
- [ ] Repeated failed logins for an identifier are throttled/locked per a defined policy.
- [ ] Legitimate login after the window/lock succeeds.
- [ ] The policy is configurable; covered by a test asserting throttle after N failures.

## Blocked by
- None - can start immediately
